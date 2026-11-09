"""Костюмы одной картинкой (09.11): промпты FLUX.3 Klein - перерисовка классики куклы. Запуск - suit_run.py.
Голые тела в hd - с маленькими чёрными наклейками и узкими стрингами (DECISIONS 2026-11-03)."""
OUT = r"E:\tmp\doll_ingame\suit"
REPAINT = ("Repaint this blurry low-resolution game sprite as a sharp, detailed, realistic painting in the style of a dark "
           "science-fiction strategy game. Keep the composition exactly: the figure in the same place, the same size, the "
           "same pose and the same outline, every part where it is now, the same colours. The plain flat grey panel around "
           "it stays exactly as it is: no floor, no shadow, no background objects. Soft light from the upper left. Crisp "
           "and sharp, no text. ")
STAND = "Front view, standing straight, arms down at the sides. "
ADULT = "An adult woman. "
WHAT = {
    "AuroraDollMDFInventoryImage": ADULT + STAND + "A pale-skinned android woman with long straight white hair, a black "
        "choker, a tiny black bikini, black fingerless gloves, black straps on one thigh and black ankle straps, barefoot.",
    "GnomeMiningSuitInventoryImage": STAND + "A squat heavy mining exosuit of glossy dark green bulbous armour plates "
        "covered in rivets, a round dome helmet with a small dark visor, big rounded shoulders, short thick legs. No skin.",
    "KillbotInventoryImage": STAND + "A slim green combat robot: glossy bright green armour plates over a black frame, a "
        "narrow head with one round red eye and two thin antennae, a small red light on the chest.",
    "MAN_1000.SPK": "A flat black hover disc seen from the front and above: a wide dark glossy saucer with two thin glowing "
        "blue rings along its rim and a pair of short dark violet twin gun barrels mounted on top. No people.",
    "MAN_1001.SPK": "A flat black hover disc seen from the front and above: a wide dark glossy saucer with two thin glowing "
        "blue rings along its rim, a dark violet double rocket launcher block with small red lights mounted on top. No people.",
    "MAN_104.SPK": STAND + "A person in a puffy red hooded winter parka with the hood up, a black face mask, black gloves, "
        "padded teal trousers and dark red boots.",
    "MAN_105.SPK": STAND + "A person in a bulky white space suit with a gold reflective round helmet visor, a dark chest "
        "harness and pack, a small green patch on the left shoulder, white padded gloves and boots.",
    "MAN_1101.SPK": "A big four-legged mutant hound with a wide toothy mouth and orange eyes, wearing heavy grey metal "
        "armour plates with spikes on its back and head, orange-brown skin on the legs, front view. No people.",
    "MAN_186.SPK": STAND + "A person in an old orange-brown diving suit with a round brass diving helmet and a small round "
        "window, a belt of square pouches, dark green boots.",
    "MAN_208.SPK": STAND + "A huge demonic power armour of black and dark red metal: curled horns on the helmet, spiked "
        "shoulder plates, glowing red cracks between the plates, heavy gauntlets and boots.",
    "MAN_496.SPK": ADULT + STAND + "A woman made of glossy translucent violet slime, wild violet hair, drops of slime "
        "dripping from her arms and legs, small black pasties on the nipples and a narrow black thong.",
    "MAN_507.SPK": STAND + "A crusader knight: a black flat-topped great helm, a long black chain mail coat, a white "
        "tabard with a red cross, gold trim on the shoulders, a black belt, black gauntlets and boots.",
    "MAN_511.SPK": ADULT + STAND + "A dark-skinned woman with long black curly hair in a superhero costume: a green top "
        "with a white ring emblem on the chest, green briefs, black sleeves and leggings, white gloves, green boots, a "
        "small green mask over the eyes.",
    "MAN_517.SPK": STAND + "A crusader knight: a black flat-topped great helm, a long black chain mail coat, a white "
        "tabard with a red cross, gold trim on the shoulders, holding a large worn wooden and gold kite shield on the "
        "right side.",
    "MAN_519.SPK": STAND + "A person in bulky pale ivory plate armour with a wide brimmed white hat and a white beard-like "
        "face guard, the armour plates shaded in light grey.",
    "MAN_529.SPK": STAND + "A soldier in a blue and grey camouflage suit with an orange padded vest, a blue helmet with "
        "an orange visor, purple gloves, brown boots.",
    "MAN_532.SPK": STAND + "A soldier in dark desert gear: a brown hood and a gas mask with big round blue lenses, a red "
        "scarf, dark armour with pouches and belts, a sand-coloured belt pack, black boots.",
    "MAN_543.SPK": STAND + "A sky knight in dark armour with a large red cloak, a helmet with a dark blue face plate and "
        "small blue wings at the sides, a glowing yellow lamp on top of the helmet and on the chest.",
    "MAN_547.SPK": STAND + "A huge heavy power armour of worn dark grey steel: rounded massive shoulder plates, a small "
        "head with two orange eye slits sunk between the shoulders, thick arms and legs.",
    "MAN_548.SPK": STAND + "A heavy power armour: a crimson red chest plate with orange trim, grey armoured arms and "
        "legs, a round dark grey helmet with an orange ring, a small pack on top, purple gloves.",
    "MAN_578.SPK": STAND + "A sleek black assault armour for a woman: dark grey and black plates, a black helmet with a "
        "violet visor and blue eyes, a small green light at the side of the helmet, violet joints.",
    "MAN_621.SPK": STAND + "A person in a glossy royal blue armoured suit with a pointed blue helmet, grey tubes over the "
        "chest, red gloves and red boots.",
    "MAN_674.SPK": ADULT + "Seen from behind and a little to the side, standing. A slim woman in a glossy dark violet "
        "skin-tight suit with black and cyan armour pieces along the spine and limbs, a round glossy dark blue helmet.",
    "MAN_675.SPK": ADULT + "Seen from behind and a little to the side, standing. A slim woman in a glossy dark violet "
        "skin-tight space suit with dark grey armour pieces along the spine and limbs, a round glossy dark blue helmet "
        "with a thin green line.",
    "MAN_69.SPK": "A low rounded green bio-tank seen from the front and above: bulging dark green organic armour like a "
        "turtle shell, a brown dome on top with a short thick brown cannon. No people.",
    "MAN_725.SPK": STAND + "A snake-woman in cyan-blue dragon armour: a cyan helmet with a red face plate, big cyan "
        "shoulder plates, a yellow tabard with a blue emblem hanging from the belt, and a long cyan armoured snake tail "
        "coiled at the bottom to the right instead of legs.",
    "MAN_741.SPK": STAND + "A snake-woman in a beige and tan space suit with a dark round helmet visor, yellow lamps on "
        "the shoulders, a beige chest pack and pouches, and a long ribbed beige snake tail at the bottom to the right "
        "instead of legs.",
    "MAN_832.SPK": STAND + "A huge black skeletal power armour: a wide horned black helmet with two small red eyes, "
        "black and silver bone-like plates, red cables, round silver knee plates, heavy clawed hands.",
    "MAN_85.SPK": "A futuristic violet motorbike with a big black rear wheel and a glossy purple fairing, a rider leaning "
        "low over it, side view.",
    "MAN_859.SPK": STAND + "A big ogre in light grey padded armour with spikes on the right shoulder, a grey hood with "
        "a stitched face, a brown leather strap across the chest, brown bare hands.",
    "MAN_86.SPK": "A boxy light grey robot cabinet with ribbed plates on top, a small panel with red and white buttons "
        "and a blue cross and a green cross on the front, front view. No people.",
    "MAN_862.SPK": STAND + "A heavy power armour of glossy royal blue plates over a black body suit, a round blue "
        "helmet, big rounded blue shoulders, black gloves, grey knee joints.",
    "MAN_865.SPK": STAND + "A huge ogre power suit of tan beige armour plates, a small dome helmet with a teal visor, "
        "purple gloves, short thick legs.",
    "MAN_866.SPK": STAND + "A huge ogre power suit of glossy crimson red armour plates, a narrow red helmet with a green "
        "visor, massive rounded shoulders.",
    "MAN_87.SPK": STAND + "A huge heavy power armour: a dark red chest with deep ribbed plates, black massive shoulders, "
        "arms and legs, a small black helmet with a red light.",
    "MAN_88.SPK": "A red four-wheeled quad bike with black knobby tyres, a dark seat and a small headlight, seen from the "
        "front and side. No people.",
    "MAN_91.SPK": "A heavy green bombard tank seen from above at an angle: dark green camouflaged armour, a huge wide "
        "mortar barrel pointing up to the upper left, tracks at the bottom. No people.",
    "MAN_92.SPK": "A small gyrocopter with a long thin brown rotor on top, a light metal frame, a round brass tank, a tail "
        "with a small propeller at the left, a pilot in dark clothes sitting in it, side view.",
    "MAN_98.SPK": "A grey steel tank seen from the front and side, with a huge exposed pale brain on top wrapped in pipes "
        "and cables, a bulldozer blade at the front. No people.",
    "MAN_991.SPK": ADULT + STAND + "A tall demon woman formed of glossy black shadow, smooth black skin like oil, long "
        "black hair in two tails tied with red bands, glowing green eyes, black clawed hands.",
    "MAN_996.SPK": "A big four-legged mutant hound with green slimy skin, a wide flat head with small yellow eyes and a "
        "toothy mouth, thick front legs, front view. No people.",
    "MAN_997.SPK": "A big four-legged mutant hound with red-brown leathery skin, a wide toothy mouth, wearing a small "
        "metal shield generator with red lights on its back, front view. No people.",
    "MAN_998.SPK": "A large dog standing up on its hind legs, black and tan fur like a german shepherd, its mouth open "
        "showing teeth and a red tongue, front paws raised.",
    "MAN_999.SPK": "A big four-legged mutant hound with red-brown leathery skin, a wide toothy mouth with sharp teeth, "
        "small horns on its head, thick legs, front view. No people.",
    "XenforcerInventoryImage": STAND + "A huge heavy power armour of dark violet plates, a small helmet with a green "
        "glowing visor, two cables hanging from the chest, dark grey armoured arms.",
    "XenforcerZortriumInventoryImage": STAND + "A huge heavy power armour of glossy violet plates with silver edges, a "
        "small helmet with a red visor and a red light on the chest.",
}
