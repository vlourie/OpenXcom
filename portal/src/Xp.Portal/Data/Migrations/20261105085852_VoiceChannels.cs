using System;
using Microsoft.EntityFrameworkCore.Migrations;
using Npgsql.EntityFrameworkCore.PostgreSQL.Metadata;

#nullable disable

namespace Xp.Portal.Data.Migrations
{
    /// <inheritdoc />
    public partial class VoiceChannels : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<bool>(
                name: "IsPublic",
                table: "VoiceRooms",
                type: "boolean",
                nullable: false,
                defaultValue: false);

            migrationBuilder.AddColumn<string>(
                name: "Topic",
                table: "VoiceRooms",
                type: "character varying(300)",
                maxLength: 300,
                nullable: true);

            migrationBuilder.CreateTable(
                name: "RoomChannelStates",
                columns: table => new
                {
                    RoomId = table.Column<Guid>(type: "uuid", nullable: false),
                    UserId = table.Column<Guid>(type: "uuid", nullable: false),
                    LastReadId = table.Column<long>(type: "bigint", nullable: false),
                    SeenAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    Joined = table.Column<bool>(type: "boolean", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RoomChannelStates", x => new { x.RoomId, x.UserId });
                    table.ForeignKey(
                        name: "FK_RoomChannelStates_AspNetUsers_UserId",
                        column: x => x.UserId,
                        principalTable: "AspNetUsers",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_RoomChannelStates_VoiceRooms_RoomId",
                        column: x => x.RoomId,
                        principalTable: "VoiceRooms",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "RoomMessages",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    RoomId = table.Column<Guid>(type: "uuid", nullable: false),
                    AuthorId = table.Column<Guid>(type: "uuid", nullable: false),
                    Kind = table.Column<string>(type: "character varying(16)", maxLength: 16, nullable: false),
                    Body = table.Column<string>(type: "character varying(1000)", maxLength: 1000, nullable: false),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    DeletedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    DeletedById = table.Column<Guid>(type: "uuid", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RoomMessages", x => x.Id);
                    table.ForeignKey(
                        name: "FK_RoomMessages_AspNetUsers_AuthorId",
                        column: x => x.AuthorId,
                        principalTable: "AspNetUsers",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_RoomMessages_AspNetUsers_DeletedById",
                        column: x => x.DeletedById,
                        principalTable: "AspNetUsers",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                    table.ForeignKey(
                        name: "FK_RoomMessages_VoiceRooms_RoomId",
                        column: x => x.RoomId,
                        principalTable: "VoiceRooms",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "RoomMessageTickets",
                columns: table => new
                {
                    MessageId = table.Column<long>(type: "bigint", nullable: false),
                    TicketId = table.Column<Guid>(type: "uuid", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RoomMessageTickets", x => new { x.MessageId, x.TicketId });
                    table.ForeignKey(
                        name: "FK_RoomMessageTickets_RoomMessages_MessageId",
                        column: x => x.MessageId,
                        principalTable: "RoomMessages",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_RoomMessageTickets_Tickets_TicketId",
                        column: x => x.TicketId,
                        principalTable: "Tickets",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_RoomChannelStates_SeenAt",
                table: "RoomChannelStates",
                column: "SeenAt");

            migrationBuilder.CreateIndex(
                name: "IX_RoomChannelStates_UserId",
                table: "RoomChannelStates",
                column: "UserId");

            migrationBuilder.CreateIndex(
                name: "IX_RoomMessages_AuthorId_CreatedAt",
                table: "RoomMessages",
                columns: new[] { "AuthorId", "CreatedAt" });

            migrationBuilder.CreateIndex(
                name: "IX_RoomMessages_CreatedAt",
                table: "RoomMessages",
                column: "CreatedAt");

            migrationBuilder.CreateIndex(
                name: "IX_RoomMessages_DeletedById",
                table: "RoomMessages",
                column: "DeletedById");

            migrationBuilder.CreateIndex(
                name: "IX_RoomMessages_RoomId_DeletedAt",
                table: "RoomMessages",
                columns: new[] { "RoomId", "DeletedAt" },
                filter: "\"DeletedAt\" IS NOT NULL");

            migrationBuilder.CreateIndex(
                name: "IX_RoomMessages_RoomId_Id",
                table: "RoomMessages",
                columns: new[] { "RoomId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_RoomMessageTickets_TicketId",
                table: "RoomMessageTickets",
                column: "TicketId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "RoomChannelStates");

            migrationBuilder.DropTable(
                name: "RoomMessageTickets");

            migrationBuilder.DropTable(
                name: "RoomMessages");

            migrationBuilder.DropColumn(
                name: "IsPublic",
                table: "VoiceRooms");

            migrationBuilder.DropColumn(
                name: "Topic",
                table: "VoiceRooms");
        }
    }
}
