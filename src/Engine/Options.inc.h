// Don't worry about Intellisense errors here, as this file is only used in conjunction with Options.h/Options.cpp
// To add a new option, add a new variable entry and a corresponding OptionInfo in Options.cpp

// General options
OPT int displayWidth, displayHeight, maxFrameSkip, baseXResolution, baseYResolution, baseXGeoscape, baseYGeoscape, baseXBattlescape, baseYBattlescape,
	soundVolume, musicVolume, uiVolume, audioSampleRate, audioBitDepth, audioChunkSize, pauseMode, windowedModePositionX, windowedModePositionY, FPS, FPSInactive,
	changeValueByMouseWheel, dragScrollTimeTolerance, dragScrollPixelTolerance, mousewheelSpeed, autosaveFrequency;
OPT bool fullscreen, asyncBlit, playIntro, useScaleFilter, useHQXFilter, useXBRZFilter, useOpenGL, checkOpenGLErrors, vSyncForOpenGL, useOpenGLSmoothing,
	autosave, allowResize, borderless, debug, debugUi, fpsCounter, newSeedOnLoad, keepAspectRatio, nonSquarePixelRatio,
	cursorInBlackBandsInFullscreen, cursorInBlackBandsInWindow, cursorInBlackBandsInBorderlessWindow, maximizeInfoScreens, musicAlwaysLoop, StereoSound, verboseLogging, soldierDiaries, touchEnabled,
	rootWindowedMode, lazyLoadResources, backgroundMute;
OPT std::string language, useOpenGLShader;
OPT KeyboardType keyboardMode;
OPT SaveSort saveOrder;
OPT MusicFormat preferredMusic;
OPT SoundFormat preferredSound;
OPT VideoFormat preferredVideo;
OPT SDL_GrabMode captureMouse;
OPT TextWrapping wordwrap;
OPT SDLKey keyOk, keyCancel, keyScreenshot, keyFps, keyQuickLoad, keyQuickSave;

// Geoscape options
OPT int geoClockSpeed, dogfightSpeed, geoScrollSpeed, geoDragScrollButton, geoscapeScale;
OPT bool includePrimeStateInSavedLayout, anytimePsiTraining, weaponSelfDestruction, retainCorpses, craftLaunchAlways,
	globeSurfaceCache, globeSeasons, globeDetail, globeRadarLines, globeFlightPaths, globeAllRadarsOnBaseBuild,
	storageLimitsEnforced, canSellLiveAliens, canTransferCraftsWhileAirborne, customInitialBase, aggressiveRetaliation, geoDragScrollInvert,
	allowBuildingQueue, showFundsOnGeoscape, psiStrengthEval, allowPsiStrengthImprovement, fieldPromotions, meetingPoint;
OPT SDLKey keyGeoLeft, keyGeoRight, keyGeoUp, keyGeoDown, keyGeoZoomIn, keyGeoZoomOut, keyGeoSpeed1, keyGeoSpeed2, keyGeoSpeed3, keyGeoSpeed4, keyGeoSpeed5, keyGeoSpeed6,
	keyGeoIntercept, keyGeoBases, keyGeoGraphs, keyGeoUfopedia, keyGeoOptions, keyGeoFunding, keyGeoToggleDetail, keyGeoToggleRadar,
	keyBaseSelect1, keyBaseSelect2, keyBaseSelect3, keyBaseSelect4, keyBaseSelect5, keyBaseSelect6, keyBaseSelect7, keyBaseSelect8;

// Battlescape options
OPT ScrollType battleEdgeScroll;
OPT PathPreview battleNewPreviewPath;
OPT int battleScrollSpeed, battleDragScrollButton, battleFireSpeed, battleXcomSpeed, battleAlienSpeed, battleExplosionHeight, battlescapeScale;
OPT bool traceAI, sneakyAI, battleInstantGrenade, battleNotifyDeath, battleTooltips, battleHairBleach, battleAutoEnd,
	strafe, forceFire, showMoreStatsInInventoryView, allowPsionicCapture, skipNextTurnScreen, disableAutoEquip, battleDragScrollInvert,
	battleUFOExtenderAccuracy, battleConfirmFireMode, battleSmoothCamera, noAlienPanicMessages, alienBleeding;
OPT SDLKey keyBattleLeft, keyBattleRight, keyBattleUp, keyBattleDown, keyBattleLevelUp, keyBattleLevelDown, keyBattleCenterUnit, keyBattlePrevUnit, keyBattleNextUnit, keyBattleDeselectUnit,
keyBattleUseLeftHand, keyBattleUseRightHand, keyBattleInventory, keyBattleMap, keyBattleOptions, keyBattleEndTurn, keyBattleAbort, keyBattleStats, keyBattleKneel,
keyBattleReserveKneel, keyBattleReload, keyBattlePersonalLighting, keyBattleReserveNone, keyBattleReserveSnap, keyBattleReserveAimed, keyBattleReserveAuto,
keyBattleCenterEnemy1, keyBattleCenterEnemy2, keyBattleCenterEnemy3, keyBattleCenterEnemy4, keyBattleCenterEnemy5, keyBattleCenterEnemy6, keyBattleCenterEnemy7, keyBattleCenterEnemy8,
keyBattleCenterEnemy9, keyBattleCenterEnemy10, keyBattleVoxelView, keyBattleZeroTUs, keyInvCreateTemplate, keyInvApplyTemplate, keyInvClear, keyInvAutoEquip,
keyBattleHdTestDump, keyBattleHdModeToggle, keyFeedback;

// Extra hotkeys (OXCE)
OPT SDLKey keyGeoDailyPilotExperience, keyGeoUfoTracker, keyGeoTechTreeViewer, keyGeoGlobalResearch, keyGeoGlobalProduction, keyGeoGlobalAlienContainment, keyGeoGlobalTransfers,
	keyGraphsZoomIn, keyGraphsZoomOut,
	keyToggleQuickSearch, keyInstaSave,
	keyCraftLoadoutSave, keyCraftLoadoutLoad,
	keyMarkAllAsSeen,
	keySellAll, keySellAllButOne,
	keyTransferAll,
	keyRemoveSoldiersFromCraft, keyRemoveSoldiersFromAllCrafts,
	keyRemoveEquipmentFromCraft,
	keyRemoveArmorFromCraft, keyRemoveArmorFromAllCrafts,
	keyRemoveSoldiersFromTraining, keyAddSoldiersToTraining,
	keyInventoryArmor, keyInventoryAvatar, keyInventoryDiaryLight, keyInventorySave, keyInventoryLoad,
	keyInvSavePersonalEquipment, keyInvLoadPersonalEquipment, keyInvShowPersonalEquipment,
	keyBattleUnitUp, keyBattleUnitDown,
	keyBattleShowLayers, keyBattlePanelHide,
	keyBattleUseSpecial,
	keyBattleActionItem1, keyBattleActionItem2, keyBattleActionItem3, keyBattleActionItem4, keyBattleActionItem5,
	keyNightVisionToggle, keyNightVisionHold, keySelectMusicTrack;
OPT SDLKey keyBasescapeBuildNewBase, keyBasescapeBaseInfo, keyBasescapeSoldiers, keyBasescapeCrafts,
	keyBasescapeFacilities, keyBasescapeResearch, keyBasescapeManufacture, keyBasescapeTransfer,
	keyBasescapePurchase, keyBasescapeSell;

// OXCE, accessible via GUI
OPT bool oxceUpdateCheck;
OPT int autosaveSlots;
OPT int oxceGeoAutosaveFrequency;
OPT int oxceGeoAutosaveSlots;
OPT bool oxceLinks;
OPT bool oxceLinksDisableTextEdit;
OPT bool oxceFatFingerLinks;
OPT bool oxceBattleTouchButtonsEnabled;
OPT bool oxceQuickSearchButton;
OPT bool oxceHighlightNewTopics;
OPT bool oxcePediaShowClipSize;
OPT int oxcePediaSortResistances; // hidden, unhide if becomes popular?

OPT int oxceInterceptTableSize;
OPT bool oxceEnableSlackingIndicator;
OPT int oxceInterceptGuiMaintenanceTime;
OPT bool oxceCraftWeaponIcons;
// HD interface: in the craft lists with the weapon icons (interception, base crafts) a disabled weapon's icon is red and a click on an icon switches that weapon on/off (the same CraftWeapon::setDisabled as the craft screens); off = as it was (default)
OPT bool oxceHdCraftWeaponToggle;
// HD interface, geoscape: a click on the funds line of the side panel shows the rating (the score the monthly report ends with) instead of the money, and back; off = as it was (default); display only
OPT bool oxceHdFundsToggle;
// HD interface, workshop: a new manufacturing job is put first in the base's list, not last (the same list order as moving it up with the arrows); the order decides who gets money and materials first; off = as it was (default)
OPT bool oxceHdManufactureTop;
// HD interface, battle inventory: the ground scroll button is drawn as two halves, an arrow to the left and an arrow to the right; a click on the left half scrolls the ground back (as the existing hidden oxceInventorySplitScrollButton does, without its picture); off = as it was (default); picture and click place only
OPT bool oxceHdScrollSplit;
OPT bool oxceDogfightHitChance;
OPT int oxceShowETAMode;
OPT bool oxceUfoLandingAlert;
OPT bool oxceRememberDisabledCraftWeapons;
OPT bool oxceGeoscapeEventsInstantDelivery;
OPT bool oxceShowBaseNameInPopups;

OPT bool oxceAlternateCraftEquipmentManagement;
OPT bool oxceBaseInfoScaleEnabled;
OPT int oxceResearchScrollSpeed;
OPT int oxceResearchScrollSpeedWithCtrl;
OPT bool oxceManufactureFilterSuppliesOK;
OPT int oxceManufactureScrollSpeed;
OPT int oxceManufactureScrollSpeedWithCtrl;
OPT bool oxcePersonalLayoutIncludingArmor;
OPT bool oxceManualPromotions;

OPT int oxceWoundedDefendBaseIf;
OPT bool oxcePlayBriefingMusicDuringEquipment;
OPT int oxceNightVisionColor;
OPT int oxceAutoNightVisionThreshold;
OPT int oxceShowAccuracyOnCrosshair;
OPT int oxceReactionFireThreshold;
OPT bool oxceAutoSell;
OPT bool oxceAutomaticPromotions;
OPT bool oxceEnableOffCentreShooting;
OPT bool oxceUniformShootingSpread;
OPT int oxceCrashedOrLanded;

namespace QOL
{
	enum class ItemTooltipMode;
	OPT int ItemTooltipMode;
	OPT int ItemTooltipHoverDelayInTenths;
	OPT SDLKey ItemTooltipHotkey;

	enum class HighlightLowManaSoldiersMode;
	OPT int highlightLowManaSoldiersMode;

	enum class DefaultSoldiersSorter;
	OPT int defaultSoldiersSorter;

	OPT bool hideEnemyTurnBackground;
	OPT int dontTraceProjectiles;
	OPT SDLKey ToggleInvidualLighting;
}

// OXCE hidden, accessible only via options.cfg
/**
 * Verification level of mod data.
 * Same levels supported as `SeverityLevel`.
 */
OPT int oxceModValidationLevel;
OPT bool oxceRawScreenShots;
OPT bool oxceFirstPersonViewFisheyeProjection;
OPT bool oxceThumbButtons;
OPT int oxceThrottleMouseMoveEvent;
OPT bool oxceDisableThinkingProgressBar;
// OXCE: forget a soldier's voice set when the player changes the avatar (so the new look gets its own voice)
OPT bool oxceResetUnitResponseSoundsOnAvatarChange;
// OXCE: the soldier list's extra column (the "sort by" choice), remembered between screens
OPT int oxceBaseSoldierInfoColumnDefault;
// Soldier lists (soldiers, craft crew): sorting puts them into groups first and keeps the chosen order inside each (0 none, 1 soldier type, 2 rank, 3 craft)
OPT int oxceBaseSoldierGroupBy;
// Soldier lists: the soldier's rank badge (its type's own set, BASEBITS) before the name
OPT bool oxceBaseSoldierTypeIcon;
OPT bool oxceTransferExchange;
// Purchase and sell: ask with the list and the total from this many chosen lines (0 - never); stay on the screen after OK
OPT int oxceTradeConfirm;
OPT bool oxceTradeStay;
// Battle inventory: a medikit, food or pills dropped on the soldier's body is taken in hand and used on them
OPT bool oxceInventoryUseOnBody;
// Battlescape (XP-000208): in the player's turn a soldier of the player's side catches an item a comrade has thrown onto his tile -
// it goes into his free hand (right, then left) for the TU of picking it up from the ground; no free hand or not enough TU - it
// lies there as before. Not for a primed item. Off by default: then nothing changes (BattlescapeGame::catchThrownItem)
OPT bool oxceCatchThrown;
// Basescape (XP-000256): a workshop order gets a Delivery button - a share of a finished batch of ordinary items goes to other bases by
// the ordinary transfer when the whole order is done. Off by default: no button, nothing is saved or sent (Production::deliver)
OPT bool oxceManufactureDelivery;
// OXCE: play cutscenes at the original 320x200 (as the classic game does); off = scaled like the geoscape
OPT bool oxceMaximizeCutsceneScreens;

OPT bool oxceEmbeddedOnly;
OPT bool oxceListVFSContents;
OPT bool oxceEnablePaletteFlickerFix;
OPT bool oxceRecommendedOptionsWereSet;
OPT std::string password;

// HD render: battlescape sprite scale (1 = classic 32x40, 2..4 = HD; needs a 32-bit display), applied at the next battle
OPT int oxceHdScale;
OPT bool oxceHdPictures;
OPT bool oxceHdUiSmooth;
/// HD interface: 0 off, 1 crisp text and nearest-scaled art, 2 crisp text and xBRZ-smoothed art.
OPT int oxceHdUi;
/// HD interface: the widget skin (0 classic shapes, 1 ramps with gradients, 2 dark panels, 3 flat).
OPT int oxceHdUiSkin;
// HD interface, modern skin (XP-000369): the windows' buttons, sliders, scroll bars and arrows in the metal of the battle panel's theme
// (oxceHdBattleHudColor) instead of the screen palette's ramp - the same on every screen. Off (default) = as it was; picture only
OPT bool oxceHdWindowTheme;
// HD interface, modern skin: the battle's button panel drawn as tiles with vector pictograms (HdBattleHud); off = the mod's picture, smoothed
OPT bool oxceHdBattleHud;
/// HD interface: 0 the game's own font, smoothed (classic colours, widths and lines); 1 TrueType (hd/UI/Font*.ttf).
OPT int oxceHdUiFont;
/// HD interface: the globe's own scale, apart from the windows around it: 0 as the geoscape, N = one globe pixel is N display pixels.
OPT int oxceHdGlobeScale;
// HD render: how the true-color battlescape canvas draws palette sprites (0 nearest, 1 HD packs, 2 HD packs + xBRZ smoothing)
OPT int oxceHdMode;
// HD render: smooth, colored light on the true-color canvas (HD modes only)
OPT bool oxceHdLight;
// HD render: the ground pattern - a floor with pack variants (<i>.v1.png ...) is laid over the map as patches
OPT bool oxceHdGroundVariants;
// HD render: a soft shadow on the floor under every visible unit standing on something (HD modes only)
OPT bool oxceHdUnitShadow;
// HD render: the floor darkens softly beside the walls and objects standing on it, by their LOFT (HD modes only)
OPT bool oxceHdFloorAo;
// HD render: a soft shadow on the floor under every item lying on it, from the alpha of its HD frame (HD modes only)
OPT bool oxceHdItemShadow;
// HD render: explosions, hits and muzzle flashes light the map around them, shadowed by its LOFT (HD modes with oxceHdLight)
OPT bool oxceHdFlashLight;
// HD render: the smoke of a tile as puffs of a baked volume that rise, grow and melt, lit where they float (HD modes, Engine/HdSmoke.h)
OPT bool oxceHdVolumeSmoke;
// HD render: the fire of a tile as tongues of flame in the pack's painted style, every tile and moment its own (HD modes, Engine/HdFire.h)
OPT bool oxceHdVolumeFire;
// HD lab (Engine/HdLab.h): the battle map turned by this many quarters (0..3), only while the lab is open
OPT int oxceHdMapRotation;
// HD lab: the key a correct lab password leaves (empty: the lab is closed)
OPT std::string oxceHdLabKey;
// HD render: SCC wall addressing - an addressed wall frame (hd/TERRAIN/<set>/address.txt) shows the picture the map's field puts in its cell (<i>.west<N>.png, <i>.north<N>.png); prototype, off, no row on the tab
OPT bool oxceHdTerrainAddress;
// HD render: the battle reticle (CURSOR.PCK 6..10): 0 the pack's own, 1 the stock picture, 2.. a style from hd/CURSOR.PCK/reticle_<style>/ (Mod::HD_RETICLES)
OPT int oxceHdReticle;
// Battlescape: the yellow reticle (CURSOR.PCK 7..10) takes the colour group the mod gives the shot's damage type in the Ufopaedia (articleItem ammoColorDT*); off = stock yellow
OPT bool oxceHdReticleDamageColor;
// HD render: the reticle of a shot of ammo that explodes (artillery) and of a thrown explosive: 0 = the main one
// (the throw cursor for the explosive), v > 0 = what oxceHdReticle value v - 1 picks (Map::updateAimHints)
OPT int oxceHdReticleArtillery;
OPT int oxceHdReticleExplosive;
// HD render, battlescape: the dashed arc a throw or an arcing shot would fly, red to where it stops when it cannot reach
OPT bool oxceHdAimArc;
// HD render, battlescape: "+N" under the reticle - the power the shooter's stats add to the aimed attack
OPT bool oxceHdAimSkillBonus;
// HD render, battlescape: the hit chance and the skill bonus at the reticle, in percent of the usual: size and stroke weight; 100 = as it was
OPT int oxceHdAimNumSize, oxceHdAimNumWeight;
// HD render, battlescape: Ctrl + mouse wheel zooms the battle view; off = Ctrl + wheel changes the level like the wheel alone
OPT bool oxceHdCtrlZoom;
// HD render, battlescape: a unit killed or knocked out by a blast is shown falling, as from a shot (XP-000252); only the picture
OPT bool oxceHdBlastFall;
// Battlescape (XP-000301): a bullet or a rocket whose ammo and weapon have no vapor in the ruleset leaves a neutral grey smoke trail (the picture
// only, with its own random generator - the battle's one is not touched; no throws, no melee, no energy beams). Off by default: then nothing changes
OPT bool oxceHdPlainSmoke;
// HD render, battlescape: the area the aimed explosive shot or throw would blast, filled on the floor in its damage type's colour, denser where the power is stronger
OPT bool oxceHdBlastArea;
// HD base screen: facility pictures play their phases (hd/BASEBITS.PCK/<i>.vN.png); off = the first phase only
OPT bool oxceHdBaseAnim;
// HD base and craft screens: the lights of the crafts (hd/BASEBITS.PCK/<i>.lights.txt) and the phases of their pictures
OPT bool oxceHdCraftLights;
// HD render: a craft sent out leaves its hangar in a clip, and lands in it the same way (hd/LAUNCH/<craft>.mpg): 0 off, 1 crafts with soldiers aboard, 2 every craft
OPT int oxceHdCraftLaunch;
OPT int oxceHdAltInfo;
// HD interface: hovering a weapon lights the ammunition that fits it (battle inventory, craft equipment, stores); off = as it was
OPT bool oxceHdAmmoHint;
OPT bool oxceHdTransferCost, oxceHdTransferConfirm;
// HD base: the craft armor screen opens sorted by craft (the "Craft" sort), off by default (XP-000345)
OPT bool oxceHdArmorSortCraft;
// HD globe and dogfight: own craft and UFOs once read by a hyper-wave decoder as small outlines from above (Engine/HdOutline.h); off = the classic markers and blob
OPT bool oxceHdCraftOutlines;
// HD globe: the crew of a player craft answers over the radio when it is picked, sent, recalled, hit or out of ammo (Engine/HdPilotVoice.h); sound only
OPT bool oxceHdPilotVoice;
// HD globe: how the radar coverage of the bases and the craft is drawn (Engine/HdRadar.h). 0 = the classic circles (default), 1 = a light wash with one joint edge, 2 = the same plus a base pulsing with each detection cycle at the slow clock speeds and a craft's beam turning (a trial)
OPT int oxceHdRadar;
// HD globe, radar 3 (waves): when the bases send their waves. 0 = all at once each game hour, 1 = in turn each hour (default), 2 = in turn each 3 hours, 3 = in turn each 6 hours
OPT int oxceHdRadarWaves;
// HD globe, radar 3 (waves): a craft out turns a beam round its circle (default) instead of sending a wave each detection cycle
OPT bool oxceHdRadarBeam;
// HD interface: the soldier transformation screen names the training paths it closes, the full list on a click (off by default)
OPT bool oxceHdTrainingBlocks;
OPT bool oxceHdPathDigits;
// HD interface: the path numbers in battle (oxceHdPathDigits on), in percent of the usual: size and stroke weight; 100 = as it was
OPT int oxceHdPathNumSize, oxceHdPathNumWeight;
OPT bool oxceHdPanelHide;
// HD interface: the path preview's arrow of a step that costs more than the usual is drawn longer (two or three arrows in a row); picture only
OPT bool oxceHdPathStretch;
// HD interface: the plate "a new update is available" in the top left corner while the launcher has written launcher/update.txt (Engine/HdUpdateNotice.h)
OPT bool oxceHdUpdateNotice;
// HD interface, craft crew screen (CraftSoldiersState): the rows of the soldiers who no longer fit the craft are grey instead of the "not enough space" window, and between the shorter sort box and OK stands a plate "seats used/seats in all"; off = as it was (default)
OPT bool oxceHdCraftFit;
// HD interface, craft crew screen (CraftSoldiersState): the name and the "WOUNDED>days" text of a wounded soldier are red; off = as it was (default); picture only
OPT bool oxceHdWoundedRed;
// HD interface, craft crew screen (CraftSoldiersState): a box "For mission:" with the detected targets; for the chosen one the names of the soldiers who can fly (starting condition: craft and soldier type) are green and a line says why not; the list is 13 rows then; off = as it was (default); picture only
OPT bool oxceHdCraftMission;
// HD interface, modern skin: the colours of the battle's button panel (Engine/HdBattleHud.cpp). 0 = dark slate (default), 1 = gold, as the original panel
OPT int oxceHdBattleHudColor;
// HD interface, modern skin (XP-000377): the player's own colour of the battle panel (oxceHdBattleHudColor 9): the keys' (and the windows' buttons') colour
// and the background's (frames, steel, wells, grooves) as hue 0-359, saturation 0-100, value 0-100; the window "Own colour" (Menu/OptionsCustomColorState)
OPT int oxceHdCustomKeyHue;
OPT int oxceHdCustomKeySat;
OPT int oxceHdCustomKeyVal;
OPT int oxceHdCustomBackHue;
OPT int oxceHdCustomBackSat;
OPT int oxceHdCustomBackVal;
// HD interface, modern skin (XP-000399): the windows' buttons cast in the battle panel's metal (oxceHdWindowTheme) get a relief
// (0 the flat button as before, 1..HdBattleHud::FACES-1 smooth, brushed, cast...), a shape (0 a chamfered plate, 1 a pillow, 2 a
// panel sunk in a rim) and a gloss 0-100 (matte to a mirror); the window "Buttons' look" (Menu/OptionsButtonFaceState); picture only
OPT int oxceHdButtonFace;
OPT int oxceHdButtonShape;
OPT int oxceHdButtonGloss;
// The same window (XP-000411): the buttons' letters (and arrows) in the theme's metal - a hue 1-360 degrees (0 = as before, picked by the
// cap) and a brightness 0-100 (50 = as before); kept readable against the cap; picture only
OPT int oxceHdButtonInkHue;
OPT int oxceHdButtonInkLight;
// The same letters, the window "Buttons' text" (XP-000399): the tone 0 auto (the theme picks light or dark by the cap, and keeps the letters
// readable) / 1 light / 2 dark (forced; readability is the player's), and the saturation 0-100 of a hue picked (75 = as before); picture only
OPT int oxceHdButtonInkTone;
OPT int oxceHdButtonInkSat;
// Battlescape sound (XP-000400): a shot's sound fades out the same sound of a shot before it still playing (a shotgun's pump heard
// over the next reaction shot); the shots keep their time and order. Off = sounds overlap, as before
OPT bool oxceHdShotCut;
// Battlescape: a unit hanging in the air or in the water with no floor below sways in place (Map::hoverBob); off = the classic still frame
OPT bool oxceHdHoverBob;
// HD render: combat effects of the HD mod (Engine/HdFx.h) - hits, swings, explosions, muzzle flashes; off = the classic animations
OPT bool oxceHdFx;
// HD render (XP-000298): the blood of a bullet hit that cost a unit health flies along the bullet's way, the more the more of its health was lost,
// in one of three variants picked by a hash of the hit (the battle's random generator is not touched); picture only. Off by default: then the same blood as before
OPT bool oxceHdBloodSpray;
// HD render (XP-000366, 367, 368): the blood of a hit on a creature in the colour the mod's table hd/blood.txt gives its armour (zombies ochre green, the deep
// ones blue, ogres and ubers dark red, machines graphite), the tone changed and the brightness kept (HdFx::bloodRgb, HdFx::tinted); picture only. Off by default: red as before
OPT bool oxceHdBloodColor;
// HD render (XP-000421): a unit that steps on the tile of a bleeding unit leaves bloody soles on its next two tiles, fading in three turns; the colour is the
// blood colour of the one who bleeds (HdFx::bloodRgb); kept in the Map only, not saved; picture only. Off by default
OPT bool oxceHdBloodSteps;
// HD render (XP-000421): how many turns the bloody soles and drops last: 1..10, 11 = always (they stay until the map's cap of prints pushes them out); default 3
OPT int oxceHdBloodStepsLife;
// HD render (XP-000421): the colour of the soles and drops: 0 by the creature (HdFx::bloodRgb with the table hd/blood.txt, whether "Blood colour by creature" is on or not),
// 1 red for all
OPT int oxceHdBloodStepsColor;
// HD render: the fire picture (SMOKE.PCK 0..7): 0 the pack's own (<i>.png, <i>.v1.png), style s = the pack's variants 2s and 2s + 1 (tools/hdart/fire_real_pack.py)
OPT int oxceHdFire;
// HD render: pace of the fire and smoke animation on tiles (Map::hdEnviClock), a step of HD_ENVI_PACE: 0 stock, higher = slower; picture only
OPT int oxceHdFirePace;
OPT int oxceHdSmokePace;
// Battlescape: the numbers above the enemies the selected unit sees (Map::setUnitMarker): 0 none, 1 blinking as the buttons, 2 steady red
OPT int oxceHdEnemyNumber;
// HD render: the final blow (Engine/HdKillCam.h) - zoom in and slow motion on the last enemy's fall; picture and pace only
OPT bool oxceHdKillCam;
// Battlescape: a long shot flies no longer than HdGentle::QUICK_FLIGHT_TICKS, and a bullet hit plays on by itself
// instead of holding up the next shot of the burst (docs/research/burst-fire-pacing.md); picture and pace only
OPT bool oxceHdQuickFlight, oxceHdLooseHits;
// Battlescape: an unseen enemy's turn shows the map as the player last saw it (the camera stays put) instead of the
// hidden movement screen; nothing the player cannot see is drawn (Map::draw). Picture only
OPT bool oxceHdHiddenMap;
// Battlescape (XP-000097), HD drawing modes: smoke, fire and lamps keep animating where the classic game stops them - while
// a battle state is busy, in the action menu over the battle, and in an unseen enemy's turn as long as nothing the player
// has discovered but does not see has changed (Map::hiddenSignature). Picture only
OPT bool oxceHdAnimHidden;
// Battlescape: the backdrop beyond the map's edge is a vertical gradient from the environment's background colour
// instead of one flat colour (Map::draw). Off by default; picture only
OPT bool oxceHdBackdrop;
// Battlescape (XP-000263), HD scale above 1: the ground goes on beyond the map's edge - the commonest floors of the map's
// edge on the ground level, laid out by a hash of the cell, fading into the backdrop with the distance. Off by default; picture only
OPT bool oxceHdBeyondEdge;
// Battlescape (XP-000380, XP-000382), HD scale above 1: the border of the battle field on the ground level, along the whole
// perimeter of the map: 0 off, 1 a line a few pixels thick just outside the edge, 2 a half-transparent red fence one level high.
// Picture only; works without oxceHdBeyondEdge
OPT int oxceHdMapBorder;
// Battlescape (XP-000263), with oxceHdBeyondEdge: the look of the ground beyond the map's edge: 0 as it is (colours, the veil of
// the backdrop's colour), 1 black and white (grey floors), 2 fog (a pale haze instead of the backdrop's colour). Picture only
OPT int oxceHdBeyondLook;
// Battlescape, what the player sees in the enemy's and the neutrals' turn: 0 as it was, 1 the hidden movement screen
// (as with oxceHdHiddenMap off) with a strip of text over it, 2 a soft red (enemy) or yellow (neutral) frame along the
// screen's edge and the panel slides down, back in the player's turn only if this slid it, 3 as 2 and a progress bar of
// the turn at the top right (the stock hidden screen's number). Picture only
OPT int oxceHdEnemyTurn;
// Ufopaedia: the weapon article's attack table has a range column (the range of the attack, at most the weapon's)
OPT bool oxceHdPediaRange;
// Battlescape: no saving or loading inside a battle (pause menu buttons, quick/insta save, quick load, turn autosave,
// the F8 report snapshot), apart from ironman; the geoscape saves as usual. Off by default; fixed while in a battle
OPT bool oxceNoBattleSaves;
// Battlescape, knowledge armor (Battlescape/KnowledgeArmor.h, Dioxine's proposal): the player's research and the enemy's
// intelligence shift how well armor stops a hit; the numbers are the ruleset's knowledgeArmor. Changes the battle; off by default
OPT bool oxceKnowledgeArmor;
// HD render: threads the battlescape frame is drawn with (0 = one per core)
OPT int oxceHdThreads;
// HD render: extra game steps a slow frame may catch up on, so that the unit speed settings hold when drawing is slower than they ask (0 = one step per frame)
OPT int oxceHdFrameSkip;
// HD render: the frame reaches the display through the video card (OpenGL 3.3 framebuffer); off - the processor scales and copies it as before
OPT bool oxceHdGpu;
// Art version currently loaded: false the ordinary HD pictures (hd/), true the adult ones (hd_18+/). Changing it reloads the resources.
OPT bool oxceAdultArt;
// Ask which art version to play at every start (AdultChoiceState). Off: play whatever oxceAdultArt says, without asking.
OPT bool oxceAdultAsk;
// The language was picked on the start screen (LanguageChoiceState); it is only asked until then. Changed later in Options > Video.
OPT bool oxceLanguageChosen;
// Gentle mode for players sensitive to flashing light (Engine/HdGentle.h): slower pace, no camera jumps. Picture and pace only.
OPT bool oxceGentle;
// The photosensitivity warning (GentleChoiceState) is shown once, until answered; then the mode is changed on the HD tab.
OPT bool oxceGentleAsk;
// Building collapse pilot (Battlescape/CollapsePilot.h): the barn house and the bunker fall apart when their supports are gone. Off by default, not on any screen.
OPT bool oxceCollapse;
// HD sprites: a walker (drawing routine 5: sectopods, reapers, wolverines and the like) that turns on the spot treads with
// its walking frames instead of showing one frame turned; frames, turn and cost are the same. Picture only, off by default.
OPT bool oxceHdWalkerTurn;
// The screen shakes when a building collapses in sight (Map::shake, CollapsePilot): picture only, off by default and in gentle mode.
OPT bool oxceHdCollapseShake;
// How hard a tree trunk is to break with oxceCollapse on (CollapsePilot::trunkArmor): 0 as in the game, 1 armor x2,
// 2 armor x3, 3 mixed (shots x3, blasts x1.5, melee x1). Changes the battle; nothing with oxceCollapse off.
OPT int oxceHdTrunkArmor;
// BetterAI (Battlescape/AiProbe.h, the BetterAI screen of the HD tab): the master switch, off = the stock OXCE AI; under it
// the fixes of the stock AI's errors (O1-O14) and the experimental AI3. Read once, at the first battle of a run.
OPT bool oxceBetterAi;
OPT bool oxceBetterAiFixes;
OPT bool oxceBetterAiAi3;

// OXCE hidden, but moddable via fixedUserOptions and/or recommendedUserOptions
OPT int oxceStartUpTextMode;

OPT int oxceGeoscapeDebugLogMaxEntries;
OPT int oxceGeoSlowdownFactor;
OPT bool oxceGeoShowScoreInsteadOfFunds;
OPT bool oxceGeoEnableTrainingIndicator;
OPT bool oxceGeoSuppressRedundantHKAlert;
OPT bool oxceGeoSuppressLandingWithoutEquipment;
OPT bool oxceGeoGoToNearestBase;
OPT bool oxceGeoSortCraftByDistanceToTarget;

OPT int oxceBaseInfoDefenseScaleMultiplier;
OPT bool oxceBaseSoldierTransformationShowOnlyEligible;
OPT bool oxceBaseFilterResearchable;
OPT bool oxceBaseResearchReorder;
OPT bool oxceBaseManufactureReorder;
OPT bool oxceBaseManufactureFallbackButton;
OPT bool oxceBaseManufactureInfinityButton;
OPT bool oxceBaseTouchButtons;

OPT bool oxceDisableAlienInventory;
OPT bool oxceDisableHitLog;
OPT bool oxceDisableInventoryTuCost;
OPT bool oxceDisableProductionDependencyTree;
OPT bool oxceDisableStatsForNerds;
OPT bool oxceDisableTechTreeViewer;

// 0 = not persisted; 1 = persisted per battle; 2 = persisted per campaign
OPT int oxceTogglePersonalLightType;
OPT int oxceToggleNightVisionType;
OPT int oxceToggleBrightnessType;
// The player's own music (XP-000373): files in <user folder>/music (geoscape/, battle/, and the files of the folder itself for both).
// 0 off (default: nothing is scanned, the music is as it was), 1 with the game's tracks, 2 only the own ones (where there are any).
OPT int oxceUserMusic;

OPT bool oxceShowBurningAsWounded;
OPT bool oxceDisableInfoOnThrowCursor;
OPT bool oxceSwapDontReselectActions;
OPT bool oxceEnableUnitResponseSounds;
OPT int oxceVoiceVolume;
OPT int oxceHiddenMovementBackgroundChangeFrequency;
OPT bool oxceInventoryShowUnitSlot;
OPT bool oxceReplaceNotesLink;

OPT bool oxceInventorySplitScrollButton;
OPT bool oxceInventoryDropItemOverPaperdoll;
OPT bool oxceInventoryUnloadFixedWeapons;

OPT int oxceMaxEquipmentLayoutTemplates;

// Flags and other stuff that don't need OptionInfo's.
OPT bool mute, reload, newOpenGL, newScaleFilter, newHQXFilter, newXBRZFilter, newRootWindowedMode, newFullscreen, newAllowResize, newBorderless;
OPT int newDisplayWidth, newDisplayHeight, newBattlescapeScale, newGeoscapeScale, newWindowedModePositionX, newWindowedModePositionY;
OPT std::string newOpenGLShader;
OPT std::vector< std::pair<std::string, bool> > mods; // ordered list of available mods (lowest priority to highest) and whether they are active
OPT SoundFormat currentSound;

OPT int battleXcomSpeedOrig;
OPT int battleAlienSpeedOrig;
