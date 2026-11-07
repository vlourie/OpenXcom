using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using Npgsql;
using Xp.Portal.Data;

namespace Xp.Portal.Tests;

/// <summary>
/// The migration of the channels (docs/portal/VOICE_IRC.md section 2) on a database that already lives: rooms, invites and
/// people written before it stay as they were, become ordinary private rooms, and take lines at once. The database is the
/// shape of the migration before this one, filled by hand, not made by the current model.
/// </summary>
public sealed class ChannelMigrationTests : IAsyncLifetime
{
    const string Before = "20261102195613_PrivateMessages";
    const string This = "20261105085852_VoiceChannels";
    readonly string _name = "xp_mig_" + Guid.NewGuid().ToString("N")[..10];
    string Connection => new NpgsqlConnectionStringBuilder(PortalFactory.ServerConnection) { Database = _name }.ConnectionString;

    public async Task InitializeAsync()
    {
        await using var c = new NpgsqlConnection(PortalFactory.ServerConnection);
        await c.OpenAsync();
        await using var cmd = new NpgsqlCommand($"CREATE DATABASE \"{_name}\"", c);
        await cmd.ExecuteNonQueryAsync();
    }

    public async Task DisposeAsync()
    {
        NpgsqlConnection.ClearAllPools();
        await using var c = new NpgsqlConnection(PortalFactory.ServerConnection);
        await c.OpenAsync();
        await using var cmd = new NpgsqlCommand($"DROP DATABASE IF EXISTS \"{_name}\" WITH (FORCE)", c);
        await cmd.ExecuteNonQueryAsync();
    }

    PortalDb Db() => new(new DbContextOptionsBuilder<PortalDb>().UseNpgsql(Connection).Options);

    /// <summary>A row with the columns given and every other required one filled with the plainest value of its type.</summary>
    static async Task InsertAsync(NpgsqlConnection c, string table, Dictionary<string, object> given)
    {
        var required = new List<(string Name, string Type)>();
        await using (var q = new NpgsqlCommand(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = @t AND is_nullable = 'NO' AND column_default IS NULL AND is_identity = 'NO' AND is_generated = 'NEVER'", c))
        {
            q.Parameters.AddWithValue("t", table);
            await using var r = await q.ExecuteReaderAsync();
            while (await r.ReadAsync()) required.Add((r.GetString(0), r.GetString(1)));
        }
        var values = new Dictionary<string, object>(given);
        foreach (var (name, type) in required)
        {
            if (values.ContainsKey(name)) continue;
            values[name] = type switch
            {
                "uuid" => Guid.NewGuid(),
                "boolean" => false,
                "integer" or "bigint" or "smallint" => 0,
                "timestamp with time zone" => DateTimeOffset.UtcNow,
                _ => "",
            };
        }
        var cols = string.Join(", ", values.Keys.Select(k => $"\"{k}\""));
        var ps = string.Join(", ", values.Keys.Select((_, i) => $"@p{i}"));
        await using var cmd = new NpgsqlCommand($"INSERT INTO \"{table}\" ({cols}) VALUES ({ps})", c);
        var n = 0;
        foreach (var v in values.Values) cmd.Parameters.AddWithValue($"p{n++}", v);
        await cmd.ExecuteNonQueryAsync();
    }

    [Fact]
    public async Task Rooms_written_before_the_channels_stay_private_rooms_and_take_lines_and_the_step_can_be_taken_back()
    {
        var owner = Guid.NewGuid();
        var guest = Guid.NewGuid();
        var room = Guid.NewGuid();
        await using (var db = Db()) await db.GetService<IMigrator>().MigrateAsync(Before);
        Assert.False(await TableExistsAsync("RoomMessages"));

        await using (var c = new NpgsqlConnection(Connection))
        {
            await c.OpenAsync();
            foreach (var (id, name) in new[] { (owner, "Хозяин"), (guest, "Гость") })
                await InsertAsync(c, "AspNetUsers", new() { ["Id"] = id, ["UserName"] = name, ["NormalizedUserName"] = name.ToUpperInvariant(), ["DisplayName"] = name, ["SecurityStamp"] = "x", ["ConcurrencyStamp"] = "x" });
            await InsertAsync(c, "VoiceRooms", new() { ["Id"] = room, ["PublicId"] = "oldroom234", ["OwnerId"] = owner, ["Title"] = "Старая комната", ["Status"] = "Open", ["Capacity"] = 16 });
            await InsertAsync(c, "RoomInvites", new() { ["RoomId"] = room, ["UserId"] = guest, ["Status"] = "Active" });
        }

        await using (var db = Db()) await db.Database.MigrateAsync();

        await using (var db = Db())
        {
            var old = await db.VoiceRooms.SingleAsync(r => r.Id == room);
            Assert.Equal(("oldroom234", "Старая комната", false, null), (old.PublicId, old.Title, old.IsPublic, old.Topic));
            Assert.Equal(VoiceRoomStatus.Open, old.Status);
            Assert.Equal(RoomInviteStatus.Active, (await db.RoomInvites.SingleAsync(i => i.RoomId == room && i.UserId == guest)).Status);
            Assert.Empty(await db.RoomMessages.ToListAsync());

            // the old room takes a line at once, and the line goes away with the room
            db.RoomMessages.Add(new RoomMessage { RoomId = room, AuthorId = guest, Kind = ChatKinds.Text, Body = "привет", CreatedAt = DateTimeOffset.UtcNow });
            db.RoomChannelStates.Add(new RoomChannelState { RoomId = room, UserId = guest, Joined = true, SeenAt = DateTimeOffset.UtcNow });
            await db.SaveChangesAsync();
            Assert.Equal(1, await db.RoomMessages.CountAsync(m => m.RoomId == room));
            // the numbers of lines are for the cursor: they only grow
            db.RoomMessages.Add(new RoomMessage { RoomId = room, AuthorId = owner, Kind = ChatKinds.Text, Body = "здравствуй", CreatedAt = DateTimeOffset.UtcNow });
            await db.SaveChangesAsync();
            var ids = await db.RoomMessages.OrderBy(m => m.Id).Select(m => m.Id).ToListAsync();
            Assert.True(ids[0] < ids[1]);
        }

        // back one step: the lines and the new columns go, the room, the invite and the people stay
        await using (var db = Db()) await db.GetService<IMigrator>().MigrateAsync(Before);
        Assert.False(await TableExistsAsync("RoomMessages"));
        Assert.False(await TableExistsAsync("RoomChannelStates"));
        await using (var c = new NpgsqlConnection(Connection))
        {
            await c.OpenAsync();
            await using var cmd = new NpgsqlCommand("SELECT count(*) FROM \"VoiceRooms\" WHERE \"Title\" = 'Старая комната'", c);
            Assert.Equal(1L, await cmd.ExecuteScalarAsync());
        }
        // and forward again, as a deployment does after a rollback
        await using (var db = Db())
        {
            await db.GetService<IMigrator>().MigrateAsync(This);
            Assert.True(await db.VoiceRooms.AnyAsync(r => r.Id == room && !r.IsPublic));
        }
    }

    async Task<bool> TableExistsAsync(string table)
    {
        await using var c = new NpgsqlConnection(Connection);
        await c.OpenAsync();
        await using var cmd = new NpgsqlCommand("SELECT count(*) FROM information_schema.tables WHERE table_name = @t", c);
        cmd.Parameters.AddWithValue("t", table);
        return (long)(await cmd.ExecuteScalarAsync())! > 0;
    }
}
