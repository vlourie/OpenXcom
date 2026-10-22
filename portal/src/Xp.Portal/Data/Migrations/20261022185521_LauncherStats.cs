using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Xp.Portal.Data.Migrations
{
    /// <inheritdoc />
    public partial class LauncherStats : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "LauncherInstalls",
                columns: table => new
                {
                    Id = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    FirstSeen = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    LastSeen = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    LastPlayingAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    PlaySeconds = table.Column<long>(type: "bigint", nullable: false),
                    LauncherVersion = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    GameRelease = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_LauncherInstalls", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_LauncherInstalls_LastPlayingAt",
                table: "LauncherInstalls",
                column: "LastPlayingAt");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "LauncherInstalls");
        }
    }
}
