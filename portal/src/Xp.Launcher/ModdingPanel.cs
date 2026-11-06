using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Xp.Launcher.Core;
using Xp.Manifest;

namespace Xp.Launcher;

/// <summary>
/// The modding mode in the settings: the switch of this installation, a new mod from the template, the author's Lua
/// mods (docs/portal/LUA_MODS.md §4, §6). On and off go into the current build's options.cfg, the way the game's menu does.
/// </summary>
sealed class ModdingPanel : StackPanel
{
    readonly Window _owner;
    readonly Func<GamePaths?> _paths;
    readonly Func<BuildStore?> _builds;
    readonly Func<Build?> _build;
    readonly Func<Updater?> _updater;
    readonly Func<ReleaseManifest?> _release;
    readonly Action<string> _fail;
    readonly Action<string> _log;
    readonly CheckBox _mode = new() { FontSize = 13 };
    readonly StackPanel _body = new() { Spacing = 10 };
    readonly StackPanel _list = new() { Spacing = 12 };
    readonly Button _create = Skin.Btn(L.T("modding.create"), "primary");
    readonly List<Button> _writes = [];
    readonly AccountPanel _account;
    readonly Func<string?> _exe;
    readonly Settings _settings;
    Dictionary<string, LuaModRow> _offers = [];
    DateTimeOffset _looked;
    bool _looking, _sending;
    bool _writable = true;
    bool _quiet;

    // an archive can take minutes on a slow line: not the 30 seconds of the other calls
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromMinutes(15) };

    public ModdingPanel(Window owner, Func<GamePaths?> paths, Func<BuildStore?> builds, Func<Build?> build, Func<Updater?> updater,
        Func<ReleaseManifest?> release, Action<string> fail, Action<string> log, AccountPanel account, Settings settings, Func<string?> exe)
    {
        (_owner, _paths, _builds, _build, _updater, _release, _fail, _log) = (owner, paths, builds, build, updater, release, fail, log);
        (_account, _settings, _exe) = (account, settings, exe);
        Spacing = 10;
        Children.Add(Skin.H2(L.T("modding.title")));
        _mode.Content = L.T("modding.mode");
        _mode.IsCheckedChanged += async (_, _) => await ModeChangedAsync();
        Children.Add(_mode);
        Children.Add(Skin.Note(L.T("modding.hint"), 13, Skin.Text2));

        var docs = Skin.Btn(L.T("modding.docs"));
        docs.Click += (_, _) => OpenDocs();
        var journal = Skin.Btn(L.T("modding.errors"));
        journal.Click += async (_, _) => await OpenErrorsAsync();
        _create.Click += async (_, _) => await CreateAsync();
        var row = new WrapPanel { Orientation = Orientation.Horizontal };
        foreach (var b in new[] { _create, docs, journal })
        {
            b.Margin = new Thickness(0, 0, 8, 6);
            row.Children.Add(b);
        }
        _body.Children.Add(row);
        _body.Children.Add(Skin.H2(L.T("modding.myMods")));
        _body.Children.Add(_list);
        Children.Add(_body);
        Fill();
    }

    /// <summary>Under a running game or an update nothing here writes; the folder and the log still open.</summary>
    public void SetWritable(bool writable)
    {
        _writable = writable;
        _mode.IsEnabled = writable && _paths() is not null;
        _create.IsEnabled = writable;
        foreach (var b in _writes) b.IsEnabled = writable;
    }

    /// <summary>The state from the disk: the author may have added a folder or the game may have changed the list.</summary>
    public void Fill()
    {
        var paths = _paths();
        _quiet = true;
        _mode.IsChecked = paths is not null && LuaMods.ModeOn(paths);
        _quiet = false;
        _mode.IsEnabled = _writable && paths is not null;
        _body.IsVisible = _mode.IsChecked == true;
        _list.Children.Clear();
        _writes.Clear();
        if (paths is null || !_body.IsVisible) return;
        List<LocalLuaMod> mods;
        try
        {
            // only reads: this runs under a game too, and Ensure would be a write (R-179)
            var build = _builds()?.Load().Current;
            var cfg = build is not null && _builds() is { } store ? store.OptionsFile(build) : Path.Combine(paths.GameDir, "user", "options.cfg");
            mods = LuaMods.List(paths, cfg, LuaMods.MasterOf(paths, build, cfg), _updater()?.PeekState()?.Installed.Keys ?? (IEnumerable<string>)[]);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            _log("my mods not listed: " + e.Message);
            return;
        }
        if (mods.Count == 0) _list.Children.Add(Skin.Note(L.T("modding.none"), 13, Skin.Text2));
        foreach (var m in mods) _list.Children.Add(Row(m));
        SetWritable(_writable);
        if (mods.Count > 0) _ = LookAsync();
    }

    (PortalClient Client, string Token)? Site()
    {
        var url = _settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        if (new DeviceStore(Path.Combine(Settings.Dir, "device.json")).Load() is not { } account || !Uri.TryCreate(url, UriKind.Absolute, out var uri)) return null;
        return (new PortalClient(Http, uri), account.Token);
    }

    /// <summary>What became of the mods offered: at most once a minute, whatever redraws the list. A dead network is silence.</summary>
    async Task LookAsync()
    {
        if (_looking || DateTimeOffset.UtcNow - _looked < TimeSpan.FromMinutes(1) || Site() is not { } s) return;
        _looking = true;
        _looked = DateTimeOffset.UtcNow;
        try
        {
            // newest first: the row of a mod is about its last version
            var fresh = (await s.Client.MyLuaModsAsync(s.Token, CancellationToken.None)).GroupBy(r => r.Mod).ToDictionary(g => g.Key, g => g.First());
            if (fresh.Count == _offers.Count && fresh.All(kv => _offers.TryGetValue(kv.Key, out var was) && was == kv.Value)) return;
            _offers = fresh;
            Fill();
        }
        catch (Exception e) when (Dialogues.Failed(e)) { }
        finally { _looking = false; }
    }

    Control Row(LocalLuaMod m)
    {
        var box = new StackPanel { Spacing = 3 };
        box.Children.Add(new TextBlock { Text = m.Name + (m.Version.Length > 0 ? "  " + m.Version : ""), FontSize = 14, FontFamily = Skin.Medium, Foreground = Skin.B(Skin.Text) });
        var words = new List<string> { L.T("modding.label"), "user/mods/" + m.Folder, L.T(m.Active ? "modding.on" : "modding.off") };
        if (m.OtherMaster is { } om) words.Add(L.T("setup.ownOtherMaster", om));
        box.Children.Add(new TextBlock { Text = string.Join("  ·  ", words), FontSize = 12, TextWrapping = TextWrapping.Wrap, Foreground = Skin.B(Skin.WarnText) });
        if (_offers.TryGetValue(m.Id, out var offered))
        {
            var says = L.T("modding.offer", offered.DisplayNumber, offered.Version, L.T("modding.offer." + offered.Status));
            if (offered.Reason is { Length: > 0 } reason) says += "\n" + reason;
            box.Children.Add(new TextBlock { Text = says, FontSize = 12, TextWrapping = TextWrapping.Wrap, Foreground = Skin.B(Skin.Text2) });
        }
        var row = new WrapPanel { Orientation = Orientation.Horizontal };
        Button Small(string key, string? cls = null)
        {
            var b = Skin.Btn(L.T(key), cls, 28);
            b.FontSize = 12;
            b.Padding = new Thickness(10, 0);
            b.Margin = new Thickness(0, 4, 8, 0);
            row.Children.Add(b);
            return b;
        }
        var toggle = Small(m.Active ? "modding.turnOff" : "modding.turnOn");
        toggle.IsVisible = m.OtherMaster is null || m.Active;
        toggle.Click += (_, _) => SetActive(m);
        _writes.Add(toggle);
        Small("modding.folder").Click += (_, _) =>
        {
            if (_paths()?.Full("user/mods/" + m.Folder) is { } dir && Directory.Exists(dir)) ReportWindow.OpenUrl(dir);
        };
        Small("modding.submit").Click += async (_, _) => await SubmitAsync(m);
        var delete = Small("modding.delete", "warn");
        delete.Click += async (_, _) => await DeleteAsync(m);
        _writes.Add(delete);
        box.Children.Add(row);
        return box;
    }

    /// <summary>§8.1: the check here, every file on the screen, the author's word, and only then the archive goes.</summary>
    async Task SubmitAsync(LocalLuaMod m)
    {
        if (_sending || _paths() is not { } paths) return;
        if (!_account.Linked)
        {
            if (await new MessageDialog(L.T("modding.linkFirst"), withNo: true).ShowDialog<bool>(_owner)) await _account.StartAsync();
            return;
        }
        if (Site() is not { } s) return;
        _sending = true;
        var dir = paths.Full("user/mods/" + m.Folder);
        var archive = Path.Combine(Path.GetTempPath(), "xp-lua-" + Guid.NewGuid().ToString("N")[..8] + ".zip");
        try
        {
            var check = await Task.Run(() => LuaSubmit.Prepare(dir));
            if (_exe() is { } exe) await LuaSubmit.EngineCheckAsync(exe, dir, check, CancellationToken.None);
            var answer = await new LuaSubmitDialog(m, check).ShowDialog<LuaSubmitAnswer?>(_owner);
            if (answer is null) return;
            if (!await Task.Run(() => LuaSubmit.Pack(dir, check, archive)))
            {
                await new MessageDialog(L.T("modding.check.archive_too_large"), withNo: false).ShowDialog<bool>(_owner);
                return;
            }
            var made = await s.Client.SubmitLuaModAsync(s.Token, check, archive, answer.Description, answer.License, L.Language, null, BuiltIn.VersionText, CancellationToken.None);
            _log($"lua mod offered: {check.Meta.Id} {check.Meta.Version} as {made.DisplayNumber}");
            await new MessageDialog(L.T("modding.sent", made.DisplayNumber), withNo: false).ShowDialog<bool>(_owner);
            _looked = default;
            await LookAsync();
        }
        catch (Exception e) when (Dialogues.Failed(e))
        {
            var words = e is PortalException p && L.Has("modding.check." + p.Code) ? L.T("modding.check." + p.Code, "", "") : Dialogues.Reason(e);
            await new MessageDialog(L.T("modding.notSent", words), withNo: false).ShowDialog<bool>(_owner);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { _fail(e.Message); }
        finally
        {
            _sending = false;
            try { File.Delete(archive); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        }
    }

    async Task ModeChangedAsync()
    {
        if (_quiet || _paths() is not { } paths) return;
        bool on = _mode.IsChecked == true;
        if (on && !await new MessageDialog(L.T("modding.warn"), withNo: true).ShowDialog<bool>(_owner))
        {
            Fill();
            return;
        }
        try
        {
            LuaMods.SetMode(paths, on);
            _log("modding mode " + (on ? "on" : "off"));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { _fail(e.Message); }
        Fill();
    }

    async Task CreateAsync()
    {
        if (_paths() is not { } paths || !_writable) return;
        var name = await new TextDialog(L.T("modding.createName"), L.T("modding.createDefault")).ShowDialog<string?>(_owner);
        if (name is null) return;
        try
        {
            var store = _builds();
            var build = _build();
            var cfg = build is not null && store is not null ? store.OptionsFile(build) : Path.Combine(paths.GameDir, "user", "options.cfg");
            var release = _release();
            var folder = LuaMods.Create(paths, name, LuaMods.MasterOf(paths, build, cfg), L.Language, release is null ? null : Setup.ReservedModNames(release));
            LuaMods.WriteDocs(paths, L.Language);
            // what was just made is meant to run on the next "Play": the id is the folder, the template says so
            if (store is not null && build is not null) LuaMods.SetActive(store, build, folder, true);
            _log("lua mod created: user/mods/" + folder);
            Fill();
            ReportWindow.OpenUrl(paths.Full("user/mods/" + folder));
        }
        catch (LuaModNameTakenException e)
        {
            await new MessageDialog(L.T("modding.nameTaken", e.Folder), withNo: false).ShowDialog<bool>(_owner);
        }
        catch (UpdateBlockedException) { _fail(L.T("builds.running")); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or UnsafePathException) { _fail(e.Message); }
    }

    void SetActive(LocalLuaMod m)
    {
        if (_builds() is not { } store || _build() is not { } build) return;
        try
        {
            LuaMods.SetActive(store, build, m.Id, !m.Active);
            _log($"lua mod {m.Id} {(m.Active ? "off" : "on")} in build '{build.Id}'");
        }
        catch (UpdateBlockedException) { _fail(L.T("builds.running")); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { _fail(e.Message); }
        Fill();
    }

    async Task DeleteAsync(LocalLuaMod m)
    {
        if (_updater() is not { } updater) return;
        if (!await new MessageDialog(L.T("modding.deleteConfirm", "user/mods/" + m.Folder), withNo: true).ShowDialog<bool>(_owner)) return;
        try
        {
            if (_builds() is { } store && _build() is { } build) LuaMods.SetActive(store, build, m.Id, false);
            var removed = updater.Purge(["user/mods/" + m.Folder]);
            _log($"lua mod deleted: {string.Join(", ", removed)}");
        }
        catch (UpdateBlockedException) { _fail(L.T("builds.running")); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or InvalidOperationException) { _fail(e.Message); }
        Fill();
    }

    void OpenDocs()
    {
        if (_paths() is not { } paths) return;
        try { ReportWindow.OpenUrl(LuaMods.WriteDocs(paths, L.Language)); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { _fail(e.Message); }
    }

    async Task OpenErrorsAsync()
    {
        if (_paths() is not { } paths) return;
        var file = LuaMods.ErrorLog(paths);
        if (File.Exists(file)) ReportWindow.OpenUrl(file);
        else await new MessageDialog(L.T("modding.noErrors"), withNo: false).ShowDialog<bool>(_owner);
    }
}

sealed record LuaSubmitAnswer(string Description, string License);

/// <summary>What would go and what the check says about it, then the author's word. The answer, or null on "Cancel"; with an error there is nothing to confirm.</summary>
sealed class LuaSubmitDialog : Window
{
    public LuaSubmitDialog(LocalLuaMod m, LuaPrecheck check)
    {
        Title = L.T("title");
        Width = 620; SizeToContent = SizeToContent.Height; CanResize = false;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        var panel = new StackPanel { Margin = new Thickness(20), Spacing = 10 };
        panel.Children.Add(Skin.H2(L.T("modding.submitTitle", m.Name, m.Version)));

        static string Say(LuaNote n) => (n.File is { Length: > 0 } f ? f + ": " : "") + L.T("modding.check." + n.Code, n.Detail ?? "");
        void Notes(string head, List<LuaNote> notes, Color color)
        {
            if (notes.Count == 0) return;
            var list = new StackPanel { Spacing = 3 };
            foreach (var n in notes) list.Children.Add(new TextBlock { Text = Say(n), FontSize = 12, TextWrapping = TextWrapping.Wrap, Foreground = Skin.B(color) });
            panel.Children.Add(new TextBlock { Text = head, FontSize = 13, FontFamily = Skin.Medium, Foreground = Skin.B(color) });
            panel.Children.Add(new ScrollViewer { Content = list, MaxHeight = 130 });
        }
        Notes(L.T("modding.errorsHead"), check.Errors, Skin.WarnText);
        Notes(L.T("modding.signalsHead"), check.Signals, Skin.Text2);

        panel.Children.Add(new TextBlock { Text = L.T("modding.filesHead", check.Files.Count, L.Size(check.Total)), FontSize = 13, FontFamily = Skin.Medium, Foreground = Skin.B(Skin.Text) });
        var files = new TextBox
        {
            Text = string.Join("\n", check.Files.Select(f => $"{f.Path}  ({L.Size(f.Size)})")), IsReadOnly = true, AcceptsReturn = true, FontSize = 12, FontFamily = new FontFamily("Consolas,monospace"),
            MaxHeight = 150, TextWrapping = TextWrapping.NoWrap,
        };
        panel.Children.Add(files);

        var send = Skin.Btn(L.T("modding.send"), "primary");
        send.Margin = new Thickness(0, 0, 8, 0);
        send.IsEnabled = false;
        var cancel = Skin.Btn(L.T("cancel"));
        cancel.Click += (_, _) => Close(null);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
        buttons.Children.Add(send);
        buttons.Children.Add(cancel);

        if (check.CanSend)
        {
            var about = new TextBox { Watermark = L.T("modding.describe"), AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 80, FontSize = 13, MaxLength = 4000 };
            var license = new TextBox { Watermark = L.T("modding.license"), FontSize = 13, MaxLength = 200 };
            var rights = new CheckBox { Content = new TextBlock { Text = L.T("modding.rights"), TextWrapping = TextWrapping.Wrap }, FontSize = 13 };
            void Ready() => send.IsEnabled = rights.IsChecked == true && (about.Text ?? "").Trim().Length > 0 && (license.Text ?? "").Trim().Length > 0;
            about.TextChanged += (_, _) => Ready();
            license.TextChanged += (_, _) => Ready();
            rights.IsCheckedChanged += (_, _) => Ready();
            send.Click += (_, _) => Close(new LuaSubmitAnswer((about.Text ?? "").Trim(), (license.Text ?? "").Trim()));
            panel.Children.Add(about);
            panel.Children.Add(license);
            panel.Children.Add(rights);
            panel.Children.Add(Skin.Note(L.T("modding.afterSend"), 12, Skin.Text2));
        }
        else send.IsVisible = false;
        panel.Children.Add(buttons);
        Content = Skin.Panel(new ScrollViewer { Content = panel, MaxHeight = 680 }, new Thickness(0));
    }
}
