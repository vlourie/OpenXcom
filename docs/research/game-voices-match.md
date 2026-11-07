# Голоса игры и наши голоса

Vitali 21.10: «в игре на английском у многих героев уже есть голоса — подобрать такие же или максимально похожие». Клипы — `art/sfx/voicepack/game_clips.tsv` (`tools/sfx/game_voice_clips.py`), сопоставление — `tools/sfx/game_voice_match.py`. Высота — медиана F0 речи, Гц.

| Тип бойца | Клипов (речь) | Речи, с | F0 игры | Наш голос | F0 нашего |
|---|---|---|---|---|---|
| Пиратка (STR_SOLDIER и S/V/W/X/R/M) | 16 (14) | 23.5 | 180.8 | V001 Убер: наглая пиратка<br>V002 Убер: ветеранша<br>V003 Убер: фрик<br>V004 Убер: Weirdgal<br>V005 Убер: кающаяся | 216.3<br>252.8<br>280.5<br>255.7<br>234.5 |
| Раб, чистокровный, герой (SLAVE, PUREBLOOD, HERO) | 34 (32) | 80.7 | 278.9 | V006 Человек: раб-солдат<br>V007 Человек: герой | 82.4<br>109.4 |
| Крестьянка, барышня (PEASANT, DAMSEL) | 16 (11) | 15.6 | 305.9 | V008 Человек: крестьянка<br>V009 Человек: барышня | 325.0<br>230.5 |
| Гибрид мужской (HYBRID) | 8 (6) | 11.2 | 225.2 | V010 Bugeye: мужской | 91.2 |
| Гибрид женский (HYBRID) | 8 (5) | 10.3 | 307.7 | V011 Bugeye: женский | 291.2 |
| Локнар (LOKNAR) | 16 (15) | 37.7 | 352.3 | V012 Lokk’Naar: гоблинка | 227.8 |
| Гномка (GNOME) | 7 (5) | 22.4 | 262.1 | V013 Гномка | 242.8 |
| Кошкодевочки (NEKOMIMI, _O, _W, _H) | 21 (4) | 14.2 | 534.0 | V014 Нэкомими: обычная<br>V015 Нэкомими: преступница<br>V016 Нэкомими: воительница<br>V017 Нэкомими: травница | 62.5<br>247.0<br>226.5<br>323.2 |
| Огр (OGRE) | 7 (5) | 12.3 | 201.7 | V018 Огр | 105.1 |
| Киллбот (KILLBOT) | 17 (16) | 36.0 | 181.4 | V025 Киллбот / Destroid | 383.2 |
| Ксенфорсер (XENFORCER) | 9 (5) | 7.3 | 201.8 | V026 Xenforcer: робот-палач | 108.2 |

### Пиратка (STR_SOLDIER и S/V/W/X/R/M)

- `Distress/Gal Panic/Breath.wav` 4.21 с, 860.2 Гц — HAH, AH, AH, AH, AH, AH, AH, HAH, HAH, HAH!
- `Distress/Gal Panic/Finish.wav` 1.62 с, 185.1 Гц — Looks like we'll finish this later.
- `Distress/Gal Panic/getout.wav` 1.62 с, 180.8 Гц — I need to get out of here.
- `Distress/Gal Panic/hell.wav` 1.57 с, 264.8 Гц — What the hell?
- `Distress/Gal Panic/hurryup.wav` 1.54 с, 149.0 Гц — Hurry up and get started.
- `Distress/Gal Panic/loadshit.wav` 1.65 с, 144.4 Гц — What a load of crap!
- `Distress/Gal Panic/rayne1b.wav` 1.25 с, 0.0 Гц — What the fuck?
- `Distress/Gal Panic/raynec.wav` 3.2 с, 225.2 Гц — Not again, baby. I have a headache.
- `Distress/Gal Panic/useme.wav` 1.52 с, 151.2 Гц — Change how you use me.
- `Distress/Gal Panic/wrthlss.wav` 3.09 с, 142.7 Гц — You are worthless and weak.
- `Distress/Gal Berserk/bon.wav` 1.29 с, 162.5 Гц — Bon appétit!
- `Distress/Gal Berserk/fight.wav` 1.07 с, 264.8 Гц — Come out and fight like a real
- `Distress/Gal Berserk/fry.wav` 1.8 с, 149.5 Гц — Fry, you little bastard!
- `Distress/Gal Berserk/laff1.wav` 4.29 с, 719.2 Гц — Ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha ha
- `Distress/Gal Berserk/Play.wav` 0.89 с, 187.2 Гц — Play with me.
- `Distress/Gal Berserk/tohell.wav` 1.38 с, 249.2 Гц — Go back to hell!

### Раб, чистокровный, герой (SLAVE, PUREBLOOD, HERO)

- `Distress/SS Panic/3whthell.wav` 2.14 с, 280.5 Гц — What the hell is going on?
- `Distress/SS Panic/Arani.wav` 1.27 с, 275.7 Гц — A fool's errand!
- `Distress/SS Panic/BladeFukyou.wav` 1.01 с, 68.9 Гц — Fuck you!
- `Distress/SS Panic/BladeOhShit.wav` 2.59 с, 207.7 Гц — Oh shit! Oh shit! Oh shit!
- `Distress/SS Panic/evryones.wav` 1.28 с, 357.5 Гц — Everyone's bleeding
- `Distress/SS Panic/ffsmindignity2.wav` 2.79 с, 127.5 Гц — I shall never forget nor forgive this indignity.
- `Distress/SS Panic/FlyE.wav` 4.26 с, 103.0 Гц — Oh, I'm not gonna be around soon if I don't get some help here.
- `Distress/SS Panic/help4.wav` 0.62 с, 450.5 Гц — HELP!
- `Distress/SS Panic/hiiide.wav` 0.72 с, 341.4 Гц — HIDE!
- `Distress/SS Panic/lkout2.wav` 0.7 с, 402.5 Гц — LOOK OUT!
- `Distress/SS Panic/orsmsaveme2.wav` 0.92 с, 231.8 Гц — Somebody save me.
- `Distress/SS Panic/otcantblameme.wav` 3.59 с, 395.6 Гц — Why didn't you tell me, you halfwigs? Why didn't they tell me? You can't blame me for this.
- `Distress/SS Panic/otsmdeaddngr3.wav` 2.55 с, 181.9 Гц — There's no time for explanations, we're all in deadly danger!
- `Distress/SS Panic/otsmhostilepl.wav` 3.84 с, 259.5 Гц — No one is ever safe on this hostile planet. Oh, dear.
- `Distress/SS Panic/otstallthem.wav` 3.36 с, 326.0 Гц — Well, stole them! Stole them! Stole them, you stupid woman! Tell them some lies!
- `Distress/SS Panic/rtancorsow2.wav` 3.6 с, 230.5 Гц — I'm fed up with you, you rancorous, quaffered old sow!
- `Distress/SS Panic/ST-FFWrongDange.wav` 2.74 с, 0.0 Гц — This is wrong, it is dangerous, it is futile!
- `Distress/SS Panic/tdormantorgan2.wav` 4.19 с, 278.9 Гц — Get some sense in another dormant organ you keep hidden in that rat's maze of yours!
- `Distress/SS Panic/tgoodthingsend.wav` 1.42 с, 264.8 Гц — And all good things must come to an end.
- `Distress/SS Panic/Xan9.wav` 3.01 с, 185.6 Гц — We're all doomed. Run while we're still able.
- `Distress/SS Berserk/ack21.wav` 2.66 с, 343.4 Гц — All right, okay then, fine, no problem.
- `Distress/SS Berserk/bringit.wav` 0.89 с, 301.5 Гц — Bring it on!
- `Distress/SS Berserk/burnem.wav` 0.68 с, 431.4 Гц — Burn him!
- `Distress/SS Berserk/dltfuckindolt.wav` 1.62 с, 157.0 Гц — You fucking dolt.
- `Distress/SS Berserk/ffsmhowdare2.wav` 1.94 с, 449.2 Гц — How dare you?
- `Distress/SS Berserk/FlyZ.wav` 2.93 с, 784.3 Гц — Take that, and that, and that!
- `Distress/SS Berserk/JonA.wav` 3.94 с, 225.2 Гц — Rage, hate, this is your death.
- `Distress/SS Berserk/murray8.wav` 7.28 с, 690.7 Гц — and the forces of darkness will applaud me as I stride through the gates of hell, carrying your head on a pike.
- `Distress/SS Berserk/orsmstrikebold2.wav` 2.69 с, 514.5 Гц — We must strike out boldly in all directions.
- `Distress/SS Berserk/thatwasyourlife.wav` 1.94 с, 154.7 Гц — What was that? That was your life, man.
- `Distress/SS Extra/orhold2.wav` 1.41 с, 385.4 Гц — Right, right, we'll stay where you are.
- `Distress/SS Extra/orstandthere2.wav` 1.52 с, 366.9 Гц — I mean, I ain't just going to stand there.
- `Distress/SS Extra/otdontworry.wav` 2.4 с, 383.2 Гц — Oh, my God! Don't worry!
- `Distress/SS Extra/tdlehands2.wav` 3.57 с, 222.6 Гц — ...eyeball hands get in the way of the devil's work, Vaughty.

### Крестьянка, барышня (PEASANT, DAMSEL)

- `Distress/PEA Panic/ffjerinsane.wav` 1.29 с, 403.6 Гц — Are you insane?
- `Distress/PEA Panic/forgetit.wav` 1.05 с, 413.1 Гц — Forget it!
- `Distress/PEA Panic/Piss2.wav` 1.71 с, 307.7 Гц — Is this going to be much longer?
- `Distress/PEA Panic/Piss4.wav` 2.35 с, 247.7 Гц — This is nothing like I expected it to be.
- `Distress/PEA Panic/SBboring.wav` 1.18 с, 211.4 Гц — Boring.
- `Distress/PEA Panic/SBohdear.wav` 0.98 с, 215.1 Гц — Oh dear.
- `Distress/PEA Panic/SBwhatthe.wav` 0.59 с, 319.6 Гц — What the f-
- `Distress/PEA Panic/Scout_autodejectedtie02.wav` 1.28 с, 455.7 Гц — You gotta be kidding me!
- `Distress/PEA Panic/Ufemh.wav` 2.25 с, 175.2 Гц — Life was hard. Then it got harder.
- `Distress/PEA Panic/vanff1.wav` 1.4 с, 263.2 Гц — What the hell is wrong with you?
- `Distress/PEA Berserk/3eatthis.wav` 0.93 с, 305.9 Гц — Eat this!
- `Distress/PEA Berserk/PINGA.WAV` 1.48 с, 333.6 Гц — Heeeh-
- `Distress/PEA Berserk/SBhahaha.wav` 0.69 с, 0.0 Гц — Ha ha ha!
- `Distress/PEA Berserk/SBlaugh.wav` 0.7 с, 275.7 Гц — Ha ha ha ha.
- `Distress/PEA Berserk/SBsayonara.wav` 0.9 с, 225.2 Гц — Sayonara.
- `Distress/PEA Berserk/youlead.wav` 1.81 с, 282.1 Гц — Hey, fuck you, motherfucker.

### Гибрид мужской (HYBRID)

- `Distress/Hybrid M Panic/dlffholyshit.wav` 0.73 с, 0.0 Гц — Holy shit!
- `Distress/Hybrid M Panic/dlothergetalong.wav` 1.81 с, 193.8 Гц — Can't we all just get along?
- `Distress/Hybrid M Panic/dlothergetangry.wav` 1.9 с, 240.0 Гц — I can't believe I have to get angry about this shit.
- `Distress/Hybrid M Panic/dlotherwhoa.wav` 0.91 с, 802.6 Гц — AHHHHH!
- `Distress/Hybrid M Panic/dltunbelievable.wav` 0.9 с, 287.1 Гц — Unbelievable.
- `Distress/Hybrid M Berserk/RevFrF00.wav` 2.4 с, 225.2 Гц — Friendly, friendly fire.
- `Distress/Hybrid M Berserk/RevOth08.wav` 2.13 с, 291.2 Гц — Look, I'm Superman! Da-da-da-da!
- `Distress/Hybrid M Berserk/RevTnt01.wav` 2.28 с, 170.7 Гц — Take that, you random arrangement of photons!

### Гибрид женский (HYBRID)

- `Distress/Hybrid F Panic/taki2.wav` 1.5 с, 267.8 Гц — You've got to be kidding.
- `Distress/Hybrid F Panic/taki3.wav` 1.0 с, 60.3 Гц — Ridiculous.
- `Distress/Hybrid F Panic/takid.wav` 2.22 с, 213.2 Гц — Don't waste my time. Let's go.
- `Distress/Hybrid F Panic/takiw.wav` 1.0 с, 233.8 Гц — No.
- `Distress/Hybrid F Panic/tirat.wav` 2.5 с, 311.2 Гц — This is absolutely pointless!
- `Distress/Hybrid F Berserk/taki1.wav` 0.75 с, 0.0 Гц — Idiot.
- `Distress/Hybrid F Berserk/takip.wav` 1.12 с, 395.8 Гц — I'll see you next time.
- `Distress/Hybrid F Berserk/tirao.wav` 3.0 с, 307.7 Гц — Can't you all? Just shut up!

### Локнар (LOKNAR)

- `Distress/Loknar Panic/Alora5.wav` 2.26 с, 584.2 Гц — Ah! Somebody hide me!
- `Distress/Loknar Panic/Alorad.wav` 4.19 с, 321.3 Гц — So when are we going to do something? I'm ready to go.
- `Distress/Loknar Panic/boring.wav` 0.98 с, 305.9 Гц — Boring!
- `Distress/Loknar Panic/cry.wav` 3.94 с, 557.8 Гц — I'm sorry. I'm sorry. I'm sorry. I'm sorry.
- `Distress/Loknar Panic/getblownup.wav` 2.54 с, 370.1 Гц — You go first. I don't want to get blown up.
- `Distress/Loknar Panic/hardwork.wav` 3.6 с, 274.9 Гц — This is hard work. I think I'll sit down for a while.
- `Distress/Loknar Panic/linas.wav` 1.96 с, 249.2 Гц — What have I gotten myself into?
- `Distress/Loknar Panic/linat.wav` 1.77 с, 234.5 Гц — How am I going to get out of this one?
- `Distress/Loknar Panic/rubbish.wav` 1.78 с, 0.0 Гц — You're really rubbish at this.
- `Distress/Loknar Panic/sense.wav` 1.18 с, 280.5 Гц — And that doesn't even make sense.
- `Distress/Loknar Berserk/Aloraa.wav` 3.15 с, 401.3 Гц — I don't think you're happy enough. I'll teach you to be happy.
- `Distress/Loknar Berserk/curse1.wav` 2.14 с, 553.0 Гц — I don't know how that's a name!
- `Distress/Loknar Berserk/easinoff.wav` 2.4 с, 334.5 Гц — Don't count on me easing off on you.
- `Distress/Loknar Berserk/idiot.wav` 1.18 с, 502.7 Гц — You idiot!
- `Distress/Loknar Berserk/linav.wav` 3.01 с, 393.3 Гц — I can do anything I want to. Understand?
- `Distress/Loknar Berserk/smartypants.wav` 2.6 с, 302.4 Гц — Just remember who I am, smarty pants.

### Гномка (GNOME)

- `Distress/Gnome Panic/Boxxy7b.wav` 0.67 с, 731.8 Гц — Wow.
- `Distress/Gnome Panic/Boxxyab.wav` 1.8 с, 0.0 Гц — Rawr! Rawr! Rawr! Rawr!
- `Distress/Gnome Panic/Boxxybn.wav` 7.91 с, 265.5 Гц — Yeah, I'm really like, it's fun. It's cool. There it is. But it's going in right now because it's just so crazy.
- `Distress/Gnome Panic/Boxxycb.wav` 8.41 с, 223.9 Гц — You know, don't kill me, please, if you, like, you know, want to. Please don't, because I love you. You just don't know it yet.
- `Distress/Gnome Panic/ot13need.wav` 1.46 с, 458.3 Гц — Protect me, Satan!
- `Distress/Gnome Berserk/Boxxyib.wav` 2.07 с, 347.3 Гц — Ah!
- `Distress/Gnome Berserk/Boxxyrb.wav` 2.87 с, 258.8 Гц — It's kind of dark, so I don't think you can see it, but it's there.

### Кошкодевочки (NEKOMIMI, _O, _W, _H)

- `Catgrrrls/Neko Panic/CGhelp.ogg` 1.35 с, 496.9 Гц — HELP!
- `Catgrrrls/Neko Panic/CGpanic1.ogg` 3.65 с, 663.3 Гц — Ah, ah, ah, ah, ah, ah!
- `Catgrrrls/Neko Panic/CGpanic2.ogg` 2.64 с, 615.3 Гц — AHHHHHHHHHHHHHHHHHHHHH
- `Catgrrrls/Neko Panic/CGpanic3.ogg` 4.51 с, 696.7 Гц — AHHHHH! AHHHHH! AHHHHH!
- `Catgrrrls/Neko Panic/CGpanic4.ogg` 3.5 с, 740.3 Гц — AHHHHHHHHHHHHHHHHHHHHHHHHH
- `Catgrrrls/Neko Berserk/CGchangemind.ogg` 3.46 с, 371.2 Гц — I changed my mind.
- `Catgrrrls/Neko Berserk/CGisteric1.ogg` 2.86 с, 710.9 Гц — laugh laughter laughter laughter laughter laughter
- `Catgrrrls/Neko Berserk/CGisteric2.ogg` 3.74 с, 488.4 Гц — Ha ha! Ha ha ha ha!
- `Catgrrrls/Neko Berserk/CGpampam.ogg` 3.4 с, 238.6 Гц — Bow-bam-bam-bam-bam, ba-bam-bam-bam-bam
- `Catgrrrls/Neko Death/CGdeath1.ogg` 1.25 с, 532.6 Гц — AHHHHH!
- `Catgrrrls/Neko Death/CGdeath2.ogg` 1.14 с, 678.8 Гц — AHHHHHHHHH!
- `Catgrrrls/Neko Death/CGdeath3.ogg` 1.83 с, 541.9 Гц — AHHHHHHHHHHHHH
- `Catgrrrls/Neko Death/CGdeath4.ogg` 0.66 с, 738.1 Гц — AHHHHH!
- `Catgrrrls/Neko Death/CGdeath5.ogg` 1.04 с, 719.2 Гц — aaaaaaaaaa
- `Catgrrrls/Neko Death/CGdeath6.ogg` 0.55 с, 691.0 Гц — Ah!
- `Catgrrrls/Neko Death/CGdeath7.ogg` 1.77 с, 830.9 Гц — Beep
- `Catgrrrls/Neko Death/CGdeath8.ogg` 0.63 с, 805.0 Гц — Beep!
- `Catgrrrls/NekoHmmm.ogg` 0.99 с, 292.9 Гц — Awwww
- `Catgrrrls/NekoMelee.ogg` 0.69 с, 0.0 Гц — You
- `Catgrrrls/NekoNya.ogg` 0.46 с, 295.7 Гц — Nio.
- `Catgrrrls/SmallBellRinging.ogg` 3.94 с, 517.4 Гц — You

### Огр (OGRE)

- `Caleb/T0253c.wav` 1.91 с, 63.6 Гц — Ooh, this could be bad.
- `Caleb/T0270c.wav` 1.75 с, 651.9 Гц — EVERYBODY DIES!
- `Caleb/T0271c.wav` 1.48 с, 0.0 Гц — Heh heh heh heh.
- `Caleb/T0272c.wav` 1.23 с, 0.0 Гц — Ha ha ha ha ha ha!
- `Caleb/T0273c.wav` 1.37 с, 135.5 Гц — He hee hee ha ha haaa!
- `Caleb/T0276c.wav` 2.88 с, 880.3 Гц — Ha-ha-ha-ha-ha-ha-ha-ha-ha-ha-ha!
- `Caleb/T0286c.wav` 5.75 с, 267.8 Гц — It burns! AHHHHHHHHHHHHHHHHHHHHH!

### Киллбот (KILLBOT)

- `KB/KB_aim1.wav` 2.84 с, 181.4 Гц — Show them the face of their destroyer.
- `KB/KB_aim2.wav` 3.04 с, 302.4 Гц — You cannot ask for that which I give freely.
- `KB/KB_aim3.wav` 3.02 с, 212.6 Гц — The humans come to hasten their destruction.
- `KB/KB_aim4.wav` 2.4 с, 231.8 Гц — They cannot escape their fate.
- `KB/KB_aim5.wav` 2.15 с, 212.6 Гц — I FORSEE THEIR DESTRUCTION!
- `KB/KB_angry.wav` 1.65 с, 61.8 Гц — HOODIAAAAAAA
- `KB/KB_death.wav` 2.79 с, 163.5 Гц — Our time together has reached its end.
- `KB/KB_move1.wav` 1.42 с, 198.3 Гц — The logic is clear.
- `KB/KB_move2.wav` 2.91 с, 178.8 Гц — The enemy cannot hide from my sight.
- `KB/KB_move3.wav` 2.31 с, 176.2 Гц — All is clear to me now.
- `KB/KB_move4.wav` 1.24 с, 0.0 Гц — As you wish.
- `KB/KB_move5.wav` 1.72 с, 187.2 Гц — The path is clear to me.
- `KB/KB_select1.wav` 1.3 с, 181.4 Гц — How can I help?
- `KB/KB_select2.wav` 2.04 с, 86.8 Гц — I am needed elsewhere. Take me.
- `KB/KB_select3.wav` 2.11 с, 146.0 Гц — Shall I divine your next move?
- `KB/KB_select4.wav` 2.11 с, 142.3 Гц — I knew you would have need of me.
- `KB/KB_select5.wav` 2.57 с, 229.2 Гц — We face an inferior foe!

### Ксенфорсер (XENFORCER)

- `XENF/XENF_aim1.ogg` 1.18 с, 206.5 Гц — Are you ready?
- `XENF/XENF_aim2.ogg` 1.5 с, 225.2 Гц — For the Motherland!
- `XENF/XENF_aim3.ogg` 0.79 с, 229.2 Гц — Move.
- `XENF/XENF_confus.ogg` 1.63 с, 201.8 Гц — What is going on?
- `XENF/XENF_move1.ogg` 1.47 с, 180.8 Гц — Let's go, team!
- `XENF/XENF_move2.ogg` 1.5 с, 181.9 Гц — Let's go, brother!
- `XENF/XENF_move3.ogg` 0.57 с, 169.8 Гц — Duh!
- `XENF/XENF_select1.ogg` 1.04 с, 201.8 Гц — CAPITAN!
- `XENF/XENF_select2.ogg` 0.82 с, 188.9 Гц — Ready?
