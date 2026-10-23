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
// HD interface, modern skin: the colours of the battle's button panel (Engine/HdBattleHud.cpp). 0 = dark slate (default), 1 = gold, as the original panel
OPT int oxceHdBattleHudColor;
// Battlescape: a unit hanging in the air or in the water with no floor below sways in place (Map::hoverBob); off = the classic still frame
OPT bool oxceHdHoverBob;
// HD render: combat effects of the HD mod (Engine/HdFx.h) - hits, swings, explosions, muzzle flashes; off = the classic animations
OPT bool oxceHdFx;
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
// Battlescape: the backdrop beyond the map's edge is a vertical gradient from the environment's background colour
// instead of one flat colour (Map::draw). Off by default; picture only
OPT bool oxceHdBackdrop;
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
// HD render: threads the battlescape frame is drawn with (0 = one per core)
OPT int oxceHdThreads;
// HD render: extra game steps a slow frame may catch up on, so that the unit speed settings hold when drawing is slower than they ask (0 = one step per frame)
OPT int oxceHdFrameSkip;
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
