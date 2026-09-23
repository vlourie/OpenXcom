using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Xp.Portal.Data.Migrations
{
    /// <inheritdoc />
    public partial class TicketLanguage : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "Language",
                table: "Tickets",
                type: "character varying(16)",
                maxLength: 16,
                nullable: true);

            migrationBuilder.CreateIndex(
                name: "IX_Tickets_Language",
                table: "Tickets",
                column: "Language");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_Tickets_Language",
                table: "Tickets");

            migrationBuilder.DropColumn(
                name: "Language",
                table: "Tickets");
        }
    }
}
