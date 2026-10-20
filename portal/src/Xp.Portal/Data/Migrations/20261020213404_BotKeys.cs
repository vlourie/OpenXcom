using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Xp.Portal.Data.Migrations
{
    /// <inheritdoc />
    public partial class BotKeys : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "BotKeys",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    UserId = table.Column<Guid>(type: "uuid", nullable: false),
                    TokenHash = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Name = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Categories = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: false),
                    Networks = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: false),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    LastUsedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    LastIp = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    RevokedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_BotKeys", x => x.Id);
                    table.ForeignKey(
                        name: "FK_BotKeys_AspNetUsers_UserId",
                        column: x => x.UserId,
                        principalTable: "AspNetUsers",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_BotKeys_TokenHash",
                table: "BotKeys",
                column: "TokenHash",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_BotKeys_UserId",
                table: "BotKeys",
                column: "UserId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "BotKeys");
        }
    }
}
