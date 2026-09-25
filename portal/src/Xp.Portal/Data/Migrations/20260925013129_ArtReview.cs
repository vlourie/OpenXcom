using System;
using System.Collections.Generic;
using Microsoft.EntityFrameworkCore.Migrations;
using Npgsql.EntityFrameworkCore.PostgreSQL.Metadata;

#nullable disable

namespace Xp.Portal.Data.Migrations
{
    /// <inheritdoc />
    public partial class ArtReview : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "ArtPacks",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Section = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    Name = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Frames = table.Column<int>(type: "integer", nullable: false),
                    Pictures = table.Column<int>(type: "integer", nullable: false),
                    HdFrames = table.Column<int>(type: "integer", nullable: false),
                    CellShare = table.Column<double>(type: "double precision", nullable: false),
                    Cells = table.Column<long>(type: "bigint", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ArtPacks", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "PackReviews",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    UserId = table.Column<Guid>(type: "uuid", nullable: false),
                    Section = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    SetName = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    ModVersion = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Tool = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    PlanPictures = table.Column<int>(type: "integer", nullable: false),
                    FrameCount = table.Column<int>(type: "integer", nullable: false),
                    BadCount = table.Column<int>(type: "integer", nullable: false),
                    CheckedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    SubmittedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    IdempotencyKey = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true),
                    SupersededAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    RevokedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    RevokedById = table.Column<Guid>(type: "uuid", nullable: true),
                    RevokedReason = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_PackReviews", x => x.Id);
                    table.ForeignKey(
                        name: "FK_PackReviews_AspNetUsers_UserId",
                        column: x => x.UserId,
                        principalTable: "AspNetUsers",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "PackReviewFrames",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    ReviewId = table.Column<Guid>(type: "uuid", nullable: false),
                    Frame = table.Column<int>(type: "integer", nullable: false),
                    Orig = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Hd = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Verdict = table.Column<string>(type: "character varying(8)", maxLength: 8, nullable: false),
                    Reasons = table.Column<List<string>>(type: "text[]", nullable: false),
                    Note = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_PackReviewFrames", x => x.Id);
                    table.ForeignKey(
                        name: "FK_PackReviewFrames_PackReviews_ReviewId",
                        column: x => x.ReviewId,
                        principalTable: "PackReviews",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_ArtPacks_Section_Name",
                table: "ArtPacks",
                columns: new[] { "Section", "Name" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_PackReviewFrames_Hd",
                table: "PackReviewFrames",
                column: "Hd");

            migrationBuilder.CreateIndex(
                name: "IX_PackReviewFrames_Orig",
                table: "PackReviewFrames",
                column: "Orig");

            migrationBuilder.CreateIndex(
                name: "IX_PackReviewFrames_ReviewId",
                table: "PackReviewFrames",
                column: "ReviewId");

            migrationBuilder.CreateIndex(
                name: "IX_PackReviews_IdempotencyKey",
                table: "PackReviews",
                column: "IdempotencyKey");

            migrationBuilder.CreateIndex(
                name: "IX_PackReviews_Section_SetName",
                table: "PackReviews",
                columns: new[] { "Section", "SetName" });

            migrationBuilder.CreateIndex(
                name: "IX_PackReviews_UserId_Section_SetName",
                table: "PackReviews",
                columns: new[] { "UserId", "Section", "SetName" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "ArtPacks");

            migrationBuilder.DropTable(
                name: "PackReviewFrames");

            migrationBuilder.DropTable(
                name: "PackReviews");
        }
    }
}
