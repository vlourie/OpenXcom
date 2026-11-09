"""Техника (09.11): FLUX.3 Klein, перерисовка классики куклы одной картинкой. Аргументы: имена через запятую (all - все), сиды.
Вход init_<имя>.png; выход E:/tmp/doll_ingame/veh/images/<имя>_<сид>.png. Запуск через gpuq окружением diffusers."""
import json
import os
import sys

OUT = r"E:\tmp\doll_ingame\veh"
REPAINT = ("Repaint this blurry low-resolution game sprite as a sharp, detailed, realistic painting in the style of a dark "
           "science-fiction strategy game. Keep the composition exactly: the object in the same place, the same size, the "
           "same angle and the same outline, every part where it is now. The plain flat grey panel around it stays exactly "
           "as it is: no floor, no shadow, no background objects. Soft light from the upper left. Crisp and sharp, no text. ")
TANK = ("It is the front view of a heavy armoured tank: massive rounded violet-grey armour plates with dark seams, "
        "dark navy-blue track units at the bottom, a low turret on top with %s in the middle. Painted heavy metal, worn "
        "edges, no people. ")
XT = ("It is a heavy automated gun turret on a round armoured pedestal with bolted feet: weathered rusty brown-bronze "
      "metal with dark gaps, a boxy gun housing on top with %s pointing to the lower right. No people. ")
SMALL = ("It is a small smooth rounded gun turret shell shaped like a beetle: one smooth glossy egg-shaped dome of black "
         "and dark grey metal with a smooth glossy %s top plate, soft rounded curves and highlights, no flat panels, no "
         "corners, no bolts; a short thick rounded gun barrel at the front. No people. ")
WHAT = {
    "MAN_65.SPK": "It is a hover tank: a dark grey armoured pod with a round ball-shaped gun mount at the front; the gun is "
                  "only one wide plain round black hole in the middle of the ball, flush with its surface, nothing sticks "
                  "out of it - no barrel, no muzzle, no tube; the pod sits on a "
                  "wide flat glossy purple saucer-shaped hover body with a thin glowing cyan rim underneath, a red ribbed "
                  "engine at the back on the left, thin cyan drops of exhaust falling below. No people. ",
    "MAN_75.SPK": "It is a four-wheeled armoured scout car: a sloped armoured hull with a small turret and a machine gun, "
                  "worn sand-and-grey camouflage paint, black off-road tyres, two round headlights at the front. No people. ",
    "MAN_89.SPK": TANK % "a round dark blue gun muzzle and a small cluster of rocket tubes to its right",
    "MAN_90.SPK": TANK % "one wide round dark blue cannon muzzle",
    "MAN_93.SPK": TANK % "a round red laser lens",
    "XTurretInventoryImage": XT % "a short black cannon barrel",
    "XTurretLaserInventoryImage": XT % "a violet laser barrel with a red tip, a small red light on the side",
    "XTurretGaussInventoryImage": XT % "a silver gauss barrel with an orange tip, a small orange light on the side",
    "XTurretPlasmaInventoryImage": XT % "a black plasma barrel with a green tip, two red lamps on top and a green panel on the side",
    "XTurretChaingunInventoryImage": XT % "a black multi-barrel chaingun",
    "XTurretPlasmaGatlingInventoryImage": XT % "a green plasma gatling barrel, two blue lamps on top and a green panel on the side",
    "TurretInventoryImage": SMALL % "glossy green",
    "TurretRedInventoryImage": SMALL % "glossy red",
}

# запуск - veh_run.py
