using Xp.Manifest;
using Xp.ReleaseBuilder;

namespace Xp.Launcher.Core.Tests;

public sealed class ComponentTests : IDisposable
{
    readonly Fixture f = new();
    public void Dispose() => f.Dispose();

    [Fact]
    public void Metadata_is_read_the_way_oxce_reads_it()
    {
        var pz = ModMetadata.Parse("﻿name: \"X-Piratez\"\r\nversion: \"v.o1.1.1\" \r\nid: piratez\r\nisMaster: true\r\nmaster: xcom1\r\nrequiredExtendedVersion: \"8.6\"\r\n", "Piratez");
        Assert.Equal(("piratez", "X-Piratez", "v.o1.1.1", true, "xcom1", "Extended"), (pz.Id, pz.Name, pz.Version, pz.IsMaster, pz.Master, pz.Engine));

        var addon = ModMetadata.Parse("id: OAK-RU # comment\nmaster: piratez\n", "OAK patch");
        Assert.Equal(("OAK-RU", "piratez", false, ""), (addon.Id, addon.Master, addon.IsMaster, addon.Engine));

        var any = ModMetadata.Parse("id: hd\nmaster: \"*\"\nrequiredExtendedVersion: 8.7\nrequiredExtendedEngine: OXCE-HD\nautoEnable: true\n", "hd");
        Assert.Equal(("", true, "OXCE-HD", true), (any.Master, any.AnyMaster, any.Engine, any.AutoEnable));

        var bare = ModMetadata.Parse("", "SomeMod");
        Assert.Equal(("SomeMod", "xcom1", false), (bare.Id, bare.Master, bare.IsMaster));      // OXCE's defaults
        Assert.Equal("", ModMetadata.Parse("id: m\nisMaster: true\n", "m").Master);             // a master has none unless named
    }

    [Fact]
    public void Colour_markup_of_a_mod_name_does_not_reach_the_player()
    {
        // XPZ RU-patch 12.3.2 paints its name and version with the engine's "\eC\xNN ... \ecP"
        var ru = ModMetadata.Parse("name: \"XPZ \\eC\\x59Russian Patch\\ecP\"\nversion: \"\\eC\\x5012.3.2\\ecP / 19-SEP-2026\"\nid: XPZ_EX_RU-patch\n", "XPZ RU-patch");
        Assert.Equal(("XPZ Russian Patch", "12.3.2 / 19-SEP-2026"), (ru.Name, ru.Version));
        Assert.Equal("say \"hi\"", ModMetadata.Parse("name: \"say \\\"hi\\\"\" # c\n", "m").Name);
    }

    void StageEdition()
    {
        Fixture.Write(f.Stage, "openxcom_hd.exe", "engine");
        Fixture.Write(f.Stage, "common/Language/en-US.yml", "strings");
        Fixture.Write(f.Stage, "standard/xcom1/items.rul", "vanilla");
        Fixture.Write(f.Stage, "user/mods/Piratez/metadata.yml", "id: piratez\nisMaster: true\nmaster: xcom1\nrequiredExtendedVersion: \"8.6\"\n");
        Fixture.Write(f.Stage, "user/mods/Piratez/Ruleset/a.rul", "piratez rules");
        Fixture.Write(f.Stage, "user/mods/OAK patch/metadata.yml", "id: OAK-RU\nmaster: piratez\n");
        Fixture.Write(f.Stage, "user/mods/OAK patch/Language/ru.yml", "oak");
        Fixture.Write(f.Stage, "user/mods/intro/metadata.yml", "id: xp_intro\nmaster: \"*\"\n");
        Fixture.Write(f.Stage, "user/mods/intro/Resources/intro_01.png", "slide");
        Fixture.Write(f.Stage, "user/mods/hd/metadata.yml", "id: hd\nmaster: \"*\"\nversion: 2.0\nrequiredExtendedEngine: OXCE-HD\n");
        Fixture.Write(f.Stage, "user/mods/hd/hd/UI/a.png", "same picture");
        Fixture.Write(f.Stage, "user/mods/hd/hd/UI/b.png", "plain picture");
        Fixture.Write(f.Stage, "user/mods/hd/hd_18+/UI/a.png", "same picture");     // a copy: left out
        Fixture.Write(f.Stage, "user/mods/hd/hd_18+/UI/b.png", "adult picture");
        Fixture.Write(f.Stage, "user/mods/Piratez/hd/TERRAIN/X.PCK/0.png", "piratez hd tile");
    }

    ReleaseManifest BuildEdition(string id = "e1", params string[] engines)
    {
        var o = new BuildOptions { StageDir = f.Stage, Id = id, Version = "1", Line = "oxce-hd", Launch = "openxcom_hd.exe" };
        o.Engines.AddRange(engines.Length > 0 ? engines : ["Extended", "OXCE-HD"]);
        o.Components["engine"] = "8.7.0-hd";
        return f.Repo.Build(o, f.Key);
    }

    [Fact]
    public void Files_are_split_into_engine_mods_and_art_layers()
    {
        StageEdition();
        var m = BuildEdition();
        string Of(string path) => m.Files.Single(x => x.Path == path).Component;
        ComponentInfo C(string id) => m.Components.Single(c => c.Id == id);

        Assert.Equal("engine", Of("openxcom_hd.exe"));
        Assert.Equal("engine", Of("common/Language/en-US.yml"));
        Assert.Equal("engine", Of("standard/xcom1/items.rul"));
        Assert.Equal("mod.piratez", Of("user/mods/Piratez/Ruleset/a.rul"));
        Assert.Equal("mod.OAK-RU", Of("user/mods/OAK patch/Language/ru.yml"));
        Assert.Equal("mod.xp_intro", Of("user/mods/intro/Resources/intro_01.png"));
        Assert.Equal("art.hd", Of("user/mods/hd/metadata.yml"));                  // the hd mod is the art layer itself
        Assert.Equal("art.hd", Of("user/mods/Piratez/hd/TERRAIN/X.PCK/0.png"));   // any mod's hd/ tree
        Assert.Equal("art.hd18", Of("user/mods/hd/hd_18+/UI/b.png"));
        Assert.DoesNotContain(m.Files, x => x.Path == "user/mods/hd/hd_18+/UI/a.png");

        Assert.Equal((ComponentKind.Engine, "8.7.0-hd"), (C("engine").Kind, C("engine").Version));
        Assert.Equal(ComponentKind.Master, C("mod.piratez").Kind);
        Assert.Equal((ComponentKind.Addon, "piratez"), (C("mod.OAK-RU").Kind, C("mod.OAK-RU").Master));
        Assert.Equal(["engine", "mod.piratez"], C("mod.OAK-RU").Requires);
        Assert.Equal(ComponentKind.Shared, C("mod.xp_intro").Kind);
        Assert.Equal(("2.0", "OXCE-HD"), (C("art.hd").Version, C("art.hd").Engine));
        Assert.True(C("art.hd18").Adult);
        Assert.Equal(["engine", "art.hd"], C("art.hd18").Requires);
        Assert.Equal((1, (long)"adult picture".Length), (C("art.hd18").Files, C("art.hd18").Size));
        Assert.Equal("oxce-hd", m.Release.Line);
        Assert.Equal(m.Files.Count, m.Components.Sum(c => c.Files));
    }

    [Fact]
    public void Our_mods_do_not_go_into_a_release_for_meridians_engine()
    {
        StageEdition();
        var e = Assert.Throws<InvalidOperationException>(() => BuildEdition("e1", "Extended"));
        Assert.Contains("OXCE-HD", e.Message);
    }

    [Fact]
    public void A_tree_no_rule_knows_stops_the_build_unless_mapped()
    {
        StageEdition();
        Fixture.Write(f.Stage, "TFTD/readme.txt", "?");
        Assert.Throws<InvalidOperationException>(() => BuildEdition("e1"));

        var o = new BuildOptions { StageDir = f.Stage, Id = "e2", Version = "1", Launch = "openxcom_hd.exe" };
        o.Engines.AddRange(["Extended", "OXCE-HD"]);
        o.Maps["TFTD/"] = "engine";
        Assert.Equal("engine", f.Repo.Build(o, f.Key).Files.Single(x => x.Path == "TFTD/readme.txt").Component);
    }

    [Fact]
    public void Manifest_with_a_file_of_an_unknown_component_is_refused()
    {
        StageEdition();
        var m = BuildEdition();
        m.Files[0].Component = "mod.nobody";
        Assert.Throws<ManifestException>(() => ManifestValidator.Validate(m));
        m.Files[0].Component = "engine";
        m.Components.Add(new ComponentInfo { Id = "engine", Kind = ComponentKind.Engine });
        Assert.Throws<ManifestException>(() => ManifestValidator.Validate(m));
    }

    static Catalog CatalogWith(params string[] components) => new()
    {
        Lines = [new CatalogLine { Id = "oxce-hd", Engine = "OXCE-HD", Title = { ["ru"] = "X-COM HD" }, Channels = ["stable"] }],
        Presets = [new CatalogPreset { Id = "piratez-hd", Line = "oxce-hd", Components = components.ToList() }],
    };

    [Fact]
    public void Catalog_is_signed_its_sequence_grows_and_presets_are_checked()
    {
        StageEdition();
        BuildEdition();
        f.Repo.Publish("stable", "e1", f.Key);

        Assert.Equal(1, f.Repo.PublishCatalog(CatalogWith("engine", "mod.piratez", "art.hd"), f.Key).Sequence);
        Assert.Equal(2, f.Repo.PublishCatalog(CatalogWith("engine", "mod.piratez"), f.Key).Sequence);

        var bytes = File.ReadAllBytes(Path.Combine(f.RepoDir, BlobKeys.Catalog));
        var sig = File.ReadAllBytes(Path.Combine(f.RepoDir, BlobKeys.Sig(BlobKeys.Catalog)));
        Assert.True(new TrustedKeys([Convert.ToBase64String(f.PublicKey)]).Verify(bytes, sig));
        Assert.Equal(2, ManifestValidator.ParseCatalog(bytes).Sequence);

        var e = Assert.Throws<InvalidOperationException>(() => f.Repo.PublishCatalog(CatalogWith("engine", "mod.rosigma"), f.Key));
        Assert.Contains("mod.rosigma", e.Message);
        Assert.Throws<ManifestException>(() => f.Repo.PublishCatalog(new Catalog
        {
            Lines = CatalogWith().Lines,
            Presets = [new CatalogPreset { Id = "p", Line = "no-such-line", Components = ["engine"] }],
        }, f.Key));
    }
}
