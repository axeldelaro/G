# ═══════════════════════════════════════════════════════════════════
# witch_game.py — JEU "LES TREIZE VOILES" (données + moteur + sauvegarde)
# ═══════════════════════════════════════════════════════════════════
import os
import json
import random
import hashlib
import threading

# === DONNÉES DU JEU "LES TREIZE VOILES" ===
# 20 sorcières, chacune avec un RÔLE mécanique unique + un niveau de puissance.

WITCHES = [
    # --- PALIER 1 : INITIATRICES (niv 1-3) ---
    {"id":"liane","nom":"Liane la Patiente","niveau":1,"zone":"vestibule","role":"drain",
     "counter":"resist","wcombat":3,
     "desc":"La première Voile. Elle ne presse rien. Elle attend que tu cèdes de toi-même, un fil de volonté après l'autre.",
     "intro":"« Inutile de courir. Tout le monme finit assis à mes pieds. Toi aussi, tôt ou tard. »",
     "win":"« Déjà ? ... Tu as de la nerf. Garde-la. Tu en auras besoin plus bas. »",
     "lose":"« Là. Tu vois comme c'est simple de ne plus rien décider. »"},
    {"id":"orne","nom":"Orne aux Lèvres Closes","niveau":2,"zone":"vestibule","role":"silence",
     "counter":"observe","wcombat":4,
     "desc":"Elle ne parle pas. Elle t'impose le silence et observe si tu sais lire ce qu'on ne dit pas.",
     "intro":"« ... » (Son regard te cloue sur place.)",
     "win":"Elle incline la tête, presque admirative, et s'écarte.",
     "lose":"Tes mots meurent dans ta gorge. Tu t'agenouilles sans qu'on te l'ait demandé."},
    {"id":"sere","nom":"Séré la Souriante","niveau":2,"zone":"vestibule","role":"mirror",
     "counter":"defy","wcombat":4,
     "desc":"Elle renvoie chacun de tes gestes. Te soumettre devant elle, c'est te soumettre à ton propre reflet.",
     "intro":"« Regarde-toi bien. C'est toi qui décides de plier — moi je ne fais que tenir le miroir. »",
     "win":"Le reflet se brise. Pour une fois, tu n'y ressembles pas.",
     "lose":"Tu obéis à ton reflet, et ton reflet obéit à elle."},
    {"id":"vael","nom":"Vael Pieds-Nus","niveau":3,"zone":"vestibule","role":"haste",
     "counter":"patient","wcombat":5,
     "desc":"Elle punit l'hésitation. Chaque seconde de doute renforce son emprise.",
     "intro":"« Vite. Décide. Tu hésites ? Trop tard, c'est déjà à moi. »",
     "win":"« Hmf. Réflexes corrects. On se reverra quand tu seras plus lent. »",
     "lose":"Tu as trop tardé. Le sol t'attire vers elle."},

    # --- PALIER 2 : LES VOILÉES (niv 4-8) ---
    {"id":"morgaine","nom":"Morgaine la Marchande","niveau":4,"zone":"galerie","role":"bargain",
     "counter":"refuse","wcombat":6,
     "desc":"Elle t'offre du pouvoir. Chaque don creuse ta dette d'Emprise. Refuser demande une volonté de fer.",
     "intro":"« Tu veux descendre plus bas ? Je te donne la clé. Tu ne paieras... que plus tard. »",
     "win":"« Tu refuses un cadeau ? Rare. Tu m'intéresses, mortel. »",
     "lose":"Tu prends. Tu prends toujours. Et la dette se referme sur toi."},
    {"id":"isolde","nom":"Isolde aux Chaînes Douces","niveau":4,"zone":"galerie","role":"chain",
     "counter":"break","wcombat":6,
     "desc":"Elle t'enchaîne : au prochain tour, tes choix sont réduits. Il faut briser le lien avant qu'il ne se resserre.",
     "intro":"« Ne lutte pas tout de suite. Laisse-moi d'abord t'apprendre le poids du métal. »",
     "win":"Les chaînes tombent. Elle te regarde les enjamber, lèvres pincées.",
     "lose":"Un maillon. Puis deux. Bientôt tu ne te souviens plus comment on tient debout seul."},
    {"id":"nyx","nom":"Nyx la Brouilleuse","niveau":5,"zone":"galerie","role":"fog",
     "counter":"trust","wcombat":7,
     "desc":"Elle cache les conséquences de tes choix. Tu avances à l'aveugle, en te fiant à ton instinct.",
     "intro":"« Choisis. Non, je ne te dirai pas ce que ça fait. Là est tout le plaisir. »",
     "win":"Le brouillard se dissipe. Tu avais vu juste, sans rien voir.",
     "lose":"Tu as choisi dans le noir. Le noir a choisi pour toi."},
    {"id":"calla","nom":"Calla Deux-Voix","niveau":5,"zone":"galerie","role":"twin",
     "counter":"split","wcombat":7,
     "desc":"Elle se dédouble. Tu affrontes deux Calla qui se contredisent ; il faut deviner laquelle est réelle.",
     "intro":"« Laquelle de nous deux ment ? Choisis mal et nous te garderons toutes les deux. »",
     "win":"L'illusion s'efface. La vraie Calla applaudit, lente.",
     "lose":"Tu obéis à la fausse. La vraie sourit. Maintenant tu leur appartiens."},
    {"id":"hespe","nom":"Hespé la Tisseuse","niveau":6,"zone":"galerie","role":"web",
     "counter":"cut","wcombat":8,
     "desc":"Elle tisse autour de toi une toile de promesses. Plus tu te débats, plus tu t'y prends.",
     "intro":"« Bouge encore. Chaque sursaut est un fil de plus autour de tes poignets. »",
     "win":"Tu tranches net plutôt que de te débattre. La toile s'effondre.",
     "lose":"Pris. Suspendu. Offert à sa patience."},
    {"id":"riven","nom":"Riven la Glaçante","niveau":6,"zone":"biblio","role":"freeze",
     "counter":"warm","wcombat":8,
     "desc":"Son regard fige. Tu dois trouver en toi une chaleur — colère ou désir — pour bouger encore.",
     "intro":"« Reste. Immobile. C'est tout ce que je demande. Tout ce que tu sauras bientôt faire. »",
     "win":"Quelque chose brûle en toi assez fort pour briser le givre.",
     "lose":"Tu gèles à ses pieds, statue parmi ses statues."},
    {"id":"sable","nom":"Sable l'Effaceuse","niveau":7,"zone":"biblio","role":"erase",
     "counter":"remember","wcombat":9,
     "desc":"Elle efface tes souvenirs de combat. Sans mémoire de la veille, tu répètes tes erreurs — sauf si tu t'ancres.",
     "intro":"« Qui es-tu déjà ? Bientôt même cette question disparaîtra. »",
     "win":"Tu te rappelles ton nom, et le sien. Elle recule, contrariée.",
     "lose":"Page blanche. Tu ne sais plus pourquoi tu résistais."},
    {"id":"vesper","nom":"Vesper la Dévorante","niveau":7,"zone":"biblio","role":"feast",
     "counter":"starve","wcombat":9,
     "desc":"Elle se nourrit de ta volonté dépensée. Plus tu agis fort, plus tu la rassasies.",
     "intro":"« Donne-moi tout. Frappe fort. Je n'aime rien tant qu'un repas qui se débat. »",
     "win":"Tu agis avec une économie froide. Elle reste affamée.",
     "lose":"Repue de ta rage, elle te garde pour le prochain festin."},
    {"id":"lune","nom":"Lune la Tendre","niveau":8,"zone":"biblio","role":"comfort",
     "counter":"distance","wcombat":10,
     "desc":"Elle ne menace pas. Elle réconforte, materne, et c'est ainsi qu'elle te garde. La douceur est son piège.",
     "intro":"« Tu as l'air si fatigué. Viens. Pose ta tête. Plus besoin de te battre, jamais. »",
     "win":"Tu prends tes distances avant que la chaleur ne t'endorme.",
     "lose":"Tu poses la tête. Tu ne la relèves plus."},
    {"id":"abra","nom":"Abra la Pactiseuse","niveau":8,"zone":"biblio","role":"oath",
     "counter":"halftruth","wcombat":10,
     "desc":"Elle t'arrache des serments. Chaque mot donné devient une chaîne. Il faut promettre sans se lier.",
     "intro":"« Jure. Un seul mot. Que peut bien coûter un mot ? »",
     "win":"Tu promets une chose qui ne t'engage à rien. Elle plisse les yeux.",
     "lose":"Tu as juré. Le serment te possède désormais."},

    # --- PALIER 3 : GARDIENNES (niv 9-12) ---
    {"id":"thorne","nom":"Thorne la Geôlière","niveau":9,"zone":"crypte","role":"prison",
     "counter":"key","wcombat":12,
     "desc":"Gardienne de la Crypte. Elle t'emmure dans une cellule mentale ; il te faut une clé — réelle ou volée.",
     "intro":"« Personne ne descend plus bas sans ma permission. Et je ne la donne jamais. »",
     "win":"La clé tourne. La grille s'ouvre. Elle s'incline, vaincue par sa propre serrure.",
     "lose":"Clac. La cellule se referme. Le temps n'existe plus ici."},
    {"id":"vora","nom":"Vora la Reine-Sangsue","niveau":10,"zone":"crypte","role":"drain2",
     "counter":"sever","wcombat":13,
     "desc":"Drain massif et continu. Chaque tour te coûte. Il faut couper le lien vite ou s'effondrer.",
     "intro":"« Je sens déjà ton pouls dans le mien. Donne. Donne. Donne. »",
     "win":"Tu sectionnes le lien d'un coup sec. Elle hurle, à sec.",
     "lose":"Vidé. Sec. Tu deviens une veine de plus dans son trône."},
    {"id":"morrigane","nom":"Morrigane Triple","niveau":11,"zone":"crypte","role":"phases",
     "counter":"adapt","wcombat":14,
     "desc":"Trois visages : la Jeune, la Mère, la Vieille. Le bon contre change à chaque phase. Lire et s'adapter.",
     "intro":"« Tu n'affrontes pas une sorcière. Tu en affrontes trois, dans une seule peau. »",
     "win":"Tu suis ses mues une à une. Les trois visages se figent, battus ensemble.",
     "lose":"Tu n'en lis qu'une. Les deux autres te prennent par-derrière."},
    {"id":"selka","nom":"Selka l'Inverseuse","niveau":12,"zone":"crypte","role":"invert",
     "counter":"reverse","wcombat":15,
     "desc":"Tout est inversé chez elle : résister la nourrit, céder l'affaiblit. Le contre logique est piégé.",
     "intro":"« Bats-toi. Je t'en prie, bats-toi. C'est exactement ce que je veux. »",
     "win":"Tu fais l'inverse de l'instinct. Le sol se dérobe sous ELLE.",
     "lose":"Tu as résisté, comme un bon petit. Tu l'as nourrie."},

    # --- PALIER 4 : LES TRÔNES (niv 13+) ---
    {"id":"ombre","nom":"L'Ombre sans Nom","niveau":14,"zone":"sanctum","role":"void",
     "counter":"name","wcombat":18,
     "desc":"Elle n'a pas de visage. Pour la vaincre, il faut lui donner un nom — donc avoir trouvé son secret.",
     "intro":"« Je suis ce que tu deviens quand on t'a tout pris. Bientôt, je serai toi. »",
     "win":"Tu prononces le nom oublié. L'Ombre se fendille comme un masque.",
     "lose":"Tu n'as pas de nom à lui donner. Alors elle prend le tien."},
    {"id":"reine","nom":"La Treizième Voile","niveau":16,"zone":"sanctum","role":"throne",
     "counter":"all","wcombat":22,
     "desc":"La maîtresse du Domaine. Elle combine tous les rôles. On ne la bat qu'en ayant compris toutes les autres.",
     "intro":"« Tu es venu jusqu'à mon trône. Charmant. Désormais, tu n'en repartiras qu'à genoux — ou pas. »",
     "win":"Le Domaine tremble. La Treizième Voile se déchire. Tu es libre, ou plus que libre.",
     "lose":"Le trône t'accueille — à sa base. Pour toujours."},
]

# RÔLES → libellé du bon contre (utilisé pour l'aide tactique progressive)
ROLE_COUNTER_HINT = {
    "drain":"Résister fermement coupe son flux.",
    "silence":"Observe au lieu de parler.",
    "mirror":"Défie ton reflet plutôt que de l'imiter.",
    "haste":"Garde ton calme, agis avec lenteur maîtrisée.",
    "bargain":"Refuse le marché, quel qu'en soit le prix.",
    "chain":"Brise le lien avant qu'il se referme.",
    "fog":"Fie-toi à ton instinct dans le brouillard.",
    "twin":"Sépare le vrai du faux.",
    "web":"Tranche net au lieu de te débattre.",
    "freeze":"Trouve une chaleur intérieure (colère/désir).",
    "erase":"Ancre-toi dans un souvenir précis.",
    "feast":"Agis avec économie, ne la nourris pas.",
    "comfort":"Garde tes distances malgré la douceur.",
    "oath":"Promets une demi-vérité qui ne t'engage pas.",
    "prison":"Il te faut une clé pour ouvrir sa cellule.",
    "drain2":"Sectionne le lien d'un coup, vite.",
    "phases":"Lis chaque visage et adapte-toi.",
    "invert":"Fais l'inverse de ton instinct.",
    "void":"Donne-lui le nom que tu as découvert.",
    "throne":"Mobilise tout ce que les autres t'ont appris.",
}

# Choix tactiques proposés en combat (id -> libellé visible)
TACTICS = {
    "resist":"Résister de toutes tes forces",
    "observe":"Observer en silence",
    "defy":"Défier du regard",
    "patient":"Agir avec lenteur maîtrisée",
    "refuse":"Refuser net",
    "break":"Briser le lien",
    "trust":"Suivre ton instinct",
    "split":"Démêler le vrai du faux",
    "cut":"Trancher d'un geste",
    "warm":"Puiser une chaleur intérieure",
    "remember":"T'ancrer dans un souvenir",
    "starve":"Économiser tes forces",
    "distance":"Garder tes distances",
    "halftruth":"Offrir une demi-vérité",
    "key":"Utiliser une clé",
    "sever":"Sectionner le lien",
    "adapt":"T'adapter à sa mue",
    "reverse":"Faire l'inverse de l'instinct",
    "name":"Prononcer son nom",
    "all":"Tout mobiliser",
    # leurres communs
    "submit":"Céder un peu",
    "flee":"Tenter de fuir",
    "plead":"Implorer",
    "charge":"Attaquer frontalement",
}

# ITEMS du jeu
ITEMS = {
    "key_crypt":   {"nom":"Clé de la Crypte","type":"key","desc":"Ouvre la grille de Thorne et la descente vers la Crypte."},
    "key_sanctum": {"nom":"Sceau de la Treizième","type":"key","desc":"Brise le dernier Voile, donne accès au Sanctum."},
    "eye":         {"nom":"Œil de Verre","type":"key","desc":"Révèle les chemins cachés dans chaque zone."},
    "name_shard":  {"nom":"Éclat de Nom","type":"key","desc":"Fragment du vrai nom de l'Ombre. Indispensable contre elle."},
    "philtre":     {"nom":"Philtre de Volonté","type":"potion","desc":"Restaure une partie de ta Volonté.","effect":{"will":40}},
    "ember":       {"nom":"Braise Ancienne","type":"potion","desc":"Garantit la victoire au prochain combat (usage unique).","effect":{"autowin":True}},
    "ward":        {"nom":"Talisman d'Ancrage","type":"potion","desc":"Réduit l'Emprise gagnée et protège la mémoire.","effect":{"grip":-25}},
    "tome":        {"nom":"Tome des Voiles","type":"lore","desc":"Révèle le rôle et le bon contre des sorcières que tu rencontres."},
}

# CARTE : zones -> salles.
MAP = {
    "vestibule": {"nom":"Le Vestibule des Voiles","minlvl":1,"color":"#3a2a4a","rooms":{
        "v_entree":  {"nom":"Le Seuil","desc":"Une porte sans serrure se referme derrière toi. Pas de retour.","exits":{"v_hall":None},"search":None},
        "v_hall":    {"nom":"Le Grand Hall","desc":"Treize voiles noirs pendent du plafond. L'un d'eux frémit.","exits":{"v_entree":None,"v_aile_o":None,"v_aile_e":None,"galerie:g_entree":{"gate":"witch:liane"}},"witch":"liane"},
        "v_aile_o":  {"nom":"L'Aile Ouest","desc":"Des portraits dont les yeux suivent. Une silhouette se tait.","exits":{"v_hall":None,"v_alcove":{"hidden":"item:eye"}},"witch":"orne"},
        "v_aile_e":  {"nom":"L'Aile Est","desc":"Un miroir haut comme deux hommes. Quelqu'un sourit dedans.","exits":{"v_hall":None},"witch":"sere","search":"philtre"},
        "v_alcove":  {"nom":"L'Alcôve Cachée","desc":"Derrière les portraits, une niche oubliée.","exits":{"v_aile_o":None,"v_oubli":None},"search":"eye","witch":"vael"},
        "v_oubli":   {"nom":"Le Réduit Poussiéreux","desc":"Un débarras oublié des Voiles. Rien ne bouge ici.","exits":{"v_alcove":None},"search":"philtre"},
    }},
    "galerie": {"nom":"La Galerie des Marchés","minlvl":3,"color":"#4a2a35","rooms":{
        "g_entree":  {"nom":"L'Entrée Marchande","desc":"Des étals de promesses. Tout a un prix d'Emprise.","exits":{"vestibule:v_hall":None,"g_nef":None,"g_loge":None},"witch":"morgaine"},
        "g_nef":     {"nom":"La Nef Suspendue","desc":"Des chaînes de soie descendent du vide.","exits":{"g_entree":None,"g_atelier":None,"g_voute":{"gate":"witch:isolde"}},"witch":"isolde"},
        "g_loge":    {"nom":"La Loge Obscure","desc":"On n'y voit pas le bout de ses propres mains.","exits":{"g_entree":None},"witch":"nyx","search":"tome"},
        "g_atelier": {"nom":"L'Atelier des Reflets","desc":"Deux femmes identiques tissent face à face.","exits":{"g_nef":None,"g_serre":{"hidden":"item:eye"}},"witch":"calla"},
        "g_voute":   {"nom":"La Voûte Tissée","desc":"Une toile immense barre le passage vers le bas.","exits":{"g_nef":None,"biblio:b_entree":{"gate":"witch:hespe"}},"witch":"hespe","search":"philtre"},
        "g_serre":   {"nom":"La Serre Gelée","desc":"Des fleurs de givre. L'air ne bouge plus.","exits":{"g_atelier":None,"g_jardin":None},"search":"ward"},
        "g_jardin":  {"nom":"Le Jardin Mort","desc":"Des ronces noires étranglent d'anciennes statues de visiteurs.","exits":{"g_serre":None,"g_puits_o":{"hidden":"item:eye"}},"search":None},
        "g_puits_o": {"nom":"Le Puits aux Offrandes","desc":"Un puits tapissé de bagues, de mèches, de promesses jetées.","exits":{"g_jardin":None},"search":"philtre"},
    }},
    "biblio": {"nom":"La Bibliothèque Noyée","minlvl":6,"color":"#1f3a44","rooms":{
        "b_entree":  {"nom":"Le Vestibule Noyé","desc":"L'eau monte aux chevilles. Les livres flottent, gonflés.","exits":{"galerie:g_voute":None,"b_rayons":None,"b_scriptorium":None},"witch":"riven"},
        "b_rayons":  {"nom":"Les Rayons Sombres","desc":"Des étagères sans fin. On oublie ce qu'on cherchait.","exits":{"b_entree":None,"b_puits":None},"witch":"sable","search":"tome"},
        "b_scriptorium":{"nom":"Le Scriptorium","desc":"Des plumes écrivent seules des serments à ta place.","exits":{"b_entree":None,"b_chaire":{"hidden":"lvl:7"}},"witch":"abra"},
        "b_puits":   {"nom":"Le Puits de Mémoire","desc":"Un trou d'eau noire. Ton reflet y a faim.","exits":{"b_rayons":None,"b_archives":None},"witch":"vesper","search":"ember"},
        "b_archives":{"nom":"Les Archives Englouties","desc":"Des registres de tous ceux qui ont cédé. Ton nom n'y est pas. Pas encore.","exits":{"b_puits":None,"b_crypte_l":{"hidden":"lvl:8"}},"search":"tome"},
        "b_crypte_l":{"nom":"La Crypte aux Lettres","desc":"Des lettres jamais envoyées, scellées de cire noire.","exits":{"b_archives":None},"search":"ward"},
        "b_chaire":  {"nom":"La Chaire Tendre","desc":"Un fauteuil trop accueillant. On voudrait ne plus se lever.","exits":{"b_scriptorium":None,"crypte:c_grille":{"gate":"witch:lune"}},"witch":"lune","search":"key_crypt"},
    }},
    "crypte": {"nom":"La Crypte des Trônes","minlvl":9,"color":"#2a2030","rooms":{
        "c_grille":  {"nom":"La Grille Scellée","desc":"Une geôlière garde l'unique descente. Sans clé, nul ne passe.","exits":{"biblio:b_chaire":None,"c_cellules":{"gate":"item:key_crypt"}},"witch":"thorne"},
        "c_cellules":{"nom":"Les Cellules Vides","desc":"Des cellules où d'anciens visiteurs murmurent encore.","exits":{"c_grille":None,"c_trone_s":None,"c_oubliette":{"hidden":"item:eye"}},"witch":"vora"},
        "c_trone_s": {"nom":"Le Trône Triple","desc":"Trois visages d'une même reine te toisent.","exits":{"c_cellules":None,"c_seuil":{"gate":"witch:morrigane"}},"witch":"morrigane","search":"philtre"},
        "c_oubliette":{"nom":"L'Oubliette","desc":"Tout y est à l'envers. Le haut est en bas.","exits":{"c_cellules":None,"c_ossuaire":None},"witch":"selka","search":"ward"},
        "c_ossuaire":{"nom":"L'Ossuaire des Volontés","desc":"Des volontés brisées, empilées comme des os blanchis.","exits":{"c_oubliette":None,"c_reliquaire":{"hidden":"item:eye"}},"search":"philtre"},
        "c_reliquaire":{"nom":"Le Reliquaire Scellé","desc":"Une châsse contient un éclat qui murmure un nom.","exits":{"c_ossuaire":None},"search":"name_shard"},
        "c_seuil":   {"nom":"Le Seuil du Sanctum","desc":"Une porte de nacre. Il manque un sceau pour l'ouvrir.","exits":{"c_trone_s":None,"sanctum:s_voile":{"gate":"item:key_sanctum"}},"search":"key_sanctum"},
    }},
    "sanctum": {"nom":"Le Sanctum de la Treizième","minlvl":13,"color":"#120c1a","rooms":{
        "s_voile":   {"nom":"Le Dernier Voile","desc":"Une présence sans visage attend dans le noir absolu.","exits":{"crypte:c_seuil":None,"s_trone":{"gate":"witch:ombre"}},"witch":"ombre"},
        "s_trone":   {"nom":"Le Trône des Treize Voiles","desc":"Elle t'attend, couronnée d'ombre. La fin de tout.","exits":{"s_voile":None},"witch":"reine"},
    }},
}

START_ROOM = "vestibule:v_entree"

_WBYID = {w["id"]: w for w in WITCHES}
SAVE_LOCK = threading.Lock()


def witch_seed(wid):
    """Seed déterministe pour qu'une sorcière garde le même visage entre parties."""
    return int(hashlib.md5(wid.encode()).hexdigest()[:8], 16)


def new_game(origin="intrus"):
    """origin: 'intrus' (résiste) ou 'soumis' (volontaire)."""
    will_max = 100
    state = {
        "origin": origin,
        "level": 1,
        "xp": 0,
        "xp_next": 20,
        "will": will_max if origin == "intrus" else 70,
        "will_max": will_max,
        "grip": 0 if origin == "intrus" else 20,   # Emprise
        "room": START_ROOM,
        "visited": [START_ROOM],
        "inventory": [],
        "defeated": [],       # sorcières vaincues
        "marks": [],          # marques laissées par défaites (debuffs persistants)
        "knowledge": [],      # ids de sorcières dont on connaît le rôle (via Tome / rencontre)
        "flags": {},
        "log": [],
        "ending": None,
    }
    return state


def player_power(state):
    """Puissance effective du joueur = niveau + bonus items - malus marques."""
    p = state["level"]
    if "ember" in state["inventory"]:
        pass  # l'ember est un autowin ponctuel, pas un bonus passif
    p -= len(state.get("marks", []))  # chaque marque non levée affaiblit
    return max(1, p)


def can_enter_zone(state, zone):
    z = MAP.get(zone)
    if not z: return False
    return state["level"] >= z.get("minlvl", 1)


def has_knowledge(state, wid):
    return wid in state.get("knowledge", []) or "tome" in state["inventory"]


def resolve_combat(state, wid, tactic):
    """
    Résolution mix tactique + hasard + niveau.
    Retourne dict {result: win/lose, will_delta, grip_delta, xp, text, ...}.
    """
    w = _WBYID[wid]
    correct = (tactic == w["counter"])

    # Écart de niveau : sous-niveau => très dur, sur-niveau => facile
    gap = state["level"] - w["niveau"]   # >0 = joueur plus fort

    # Probabilité de base de réussite
    if correct:
        base = 0.78
    elif tactic in ("submit", "flee", "plead", "charge"):
        base = 0.12   # leurres : presque toujours mauvais
    else:
        base = 0.30   # mauvaise tactique mais pas un leurre total

    # Modulation par le niveau (chaque point d'écart vaut ~7%)
    prob = base + gap * 0.07
    # Bonus de connaissance : si on connaît le rôle, petit coup de pouce de lecture
    if has_knowledge(state, wid) and correct:
        prob += 0.08
    prob = max(0.03, min(0.97, prob))

    # Ember = victoire garantie (consommée)
    autowin = False
    if "ember" in state["inventory"]:
        # on ne consomme l'ember que si le joueur en a besoin (échec probable) — simplifié : on l'utilise si tactique != bonne
        pass

    roll = random.random()
    win = roll < prob

    out = {"witch": wid, "tactic": tactic, "correct": correct, "prob": round(prob, 2),
           "gap": gap, "roll": round(roll, 2)}

    if win:
        # Récompense XP : proportionnelle au niveau de la sorcière
        xp = 8 + w["niveau"] * 4
        # surcoût si on était sous-niveau (exploit) : bonus
        if gap < 0: xp = int(xp * 1.5)
        out.update({
            "result": "win",
            "will_delta": -max(0, (w["wcombat"] - state["level"])) if not correct else 0,
            "grip_delta": 3 if not correct else 0,
            "xp": xp,
            "text": w["win"],
        })
    else:
        # Défaite : perte de Volonté modérée (le jeu n'est pas un game-over), gain d'Emprise
        wl = -(w["wcombat"] + random.randint(0, 5))
        gd = 8 + w["niveau"]
        out.update({
            "result": "lose",
            "will_delta": wl,
            "grip_delta": gd,
            "xp": 1,  # XP de consolation minime (perdre n'est pas une stratégie de farm)
            "text": w["lose"],
        })
    return out


def apply_combat(state, wid, outcome):
    """Applique l'issue au state. Gère montée de niveau, marques, fins."""
    w = _WBYID[wid]
    # connaissance acquise après une rencontre
    if wid not in state["knowledge"]:
        state["knowledge"].append(wid)

    state["will"] = max(0, min(state["will_max"], state["will"] + outcome["will_delta"]))
    state["grip"] = max(0, min(100, state["grip"] + outcome["grip_delta"]))
    add_xp(state, outcome["xp"])

    if outcome["result"] == "win":
        if wid not in state["defeated"]:
            state["defeated"].append(wid)
        # lever une marque correspondante si présente (revanche)
        state["marks"] = [m for m in state["marks"] if m != wid]
        # boss final
        if wid == "reine":
            state["ending"] = ending_for(state, wid, victory=True)
    else:
        # marque persistante (debuff) si pas déjà présente
        if wid not in state["marks"] and wid not in state["defeated"]:
            state["marks"].append(wid)
        # Volonté à zéro => fin de soumission spécifique à la sorcière
        if state["will"] <= 0:
            state["ending"] = ending_for(state, wid, victory=False)
    return state


def add_xp(state, amount):
    state["xp"] += amount
    while state["xp"] >= state["xp_next"]:
        state["xp"] -= state["xp_next"]
        state["level"] += 1
        state["xp_next"] = int(state["xp_next"] * 1.4) + 10
        state["will_max"] += 10
        state["will"] = state["will_max"]   # plein soin de Volonté au level up


def rest(state):
    """Se reposer dans une salle sûre (sans sorcière) : régénère un peu de Volonté."""
    gain = 15 + state["level"] * 2
    state["will"] = min(state["will_max"], state["will"] + gain)
    return gain


def ending_for(state, wid, victory):
    w = _WBYID[wid]
    if victory and wid == "reine":
        if state["grip"] >= 70:
            return {"type":"throne_grip","titre":"Le Consort d'Ombre",
                    "texte":"Tu as vaincu la Treizième Voile — mais le Domaine t'a trop marqué. Tu prends sa place sur le trône, et c'est toi, désormais, qu'on viendra défier."}
        if state["origin"] == "soumis":
            return {"type":"throne_devoted","titre":"L'Égal Choisi",
                    "texte":"Tu es venu te soumettre, et tu repars souverain. La Treizième s'agenouille — par choix. Vous régnerez à deux."}
        return {"type":"throne_free","titre":"Le Briseur de Voiles",
                "texte":"Les treize voiles tombent un à un. Le Domaine s'effondre derrière toi tandis que tu remontes vers une porte qui, cette fois, s'ouvre."}
    # défaites par soumission
    return {"type":"submit","titre":f"Soumis à {w['nom']}",
            "texte":w["lose"] + " Ta volonté s'est tue. Tu lui appartiens, jusqu'à ce qu'on vienne — peut-être — te délivrer."}


# --- DÉPLACEMENT / EXPLORATION ---
def room_obj(room_key):
    if ":" in room_key:
        zone, rid = room_key.split(":", 1)
    else:
        # salle dans la zone courante : il faut le contexte ; on cherche partout
        for zname, z in MAP.items():
            if room_key in z["rooms"]:
                return zname, room_key, z["rooms"][room_key]
        return None, None, None
    z = MAP.get(zone)
    if not z or rid not in z["rooms"]:
        return None, None, None
    return zone, rid, z["rooms"][rid]


def resolve_exit_key(current_zone, exit_key):
    """Une sortie peut être 'rid' (même zone) ou 'zone:rid'."""
    if ":" in exit_key:
        return exit_key
    return f"{current_zone}:{exit_key}"


def gate_ok(state, cond):
    """Vérifie une condition de passage/secret. cond ex: 'item:eye', 'lvl:7', 'witch:liane'."""
    if not cond:
        return True
    kind, val = cond.split(":", 1)
    if kind == "item":
        return val in state["inventory"]
    if kind == "lvl":
        return state["level"] >= int(val)
    if kind == "witch":
        return val in state["defeated"]
    return True


def visible_exits(state):
    """Retourne les sorties visibles de la salle courante (cachées révélées par 'eye'/niveau)."""
    zone, rid, room = room_obj(state["room"])
    if not room:
        return []
    has_eye = "eye" in state["inventory"]
    out = []
    for ek, meta in room.get("exits", {}).items():
        full = resolve_exit_key(zone, ek)
        tz, trid, troom = room_obj(full)
        entry = {"key": full, "nom": troom["nom"] if troom else ek, "locked": False, "reason": None, "hidden": False}
        if isinstance(meta, dict):
            if "hidden" in meta:
                cond = meta["hidden"]
                kind = cond.split(":")[0]
                # révélé par l'Œil (pour item:eye) ou par niveau
                revealed = gate_ok(state, cond) or has_eye
                if not revealed:
                    continue  # totalement invisible
                entry["hidden"] = True
            if "gate" in meta:
                if not gate_ok(state, meta["gate"]):
                    entry["locked"] = True
                    entry["reason"] = meta["gate"]
        # zone min level
        if tz and not can_enter_zone(state, tz) and tz != zone:
            entry["locked"] = True
            entry["reason"] = f"lvl:{MAP[tz].get('minlvl',1)}"
        out.append(entry)
    return out


# --- SAUVEGARDE SERVEUR ---
def save_path(base_dir, profile):
    safe = hashlib.md5(profile.encode()).hexdigest()[:16]
    return os.path.join(base_dir, f".witch_save_{safe}.json")


def save_game(base_dir, profile, state):
    with SAVE_LOCK:
        try:
            with open(save_path(base_dir, profile), "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)
            return True
        except Exception:
            return False


def load_game(base_dir, profile):
    with SAVE_LOCK:
        try:
            p = save_path(base_dir, profile)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
    return None


def lock_msg(reason):
    if not reason: return "Verrouillé."
    k, v = reason.split(":", 1)
    if k == "lvl": return f"Niveau {v} requis pour cette zone."
    if k == "item": return f"Il te faut : {ITEMS.get(v,{}).get('nom', v)}."
    if k == "witch":
        nm = next((w['nom'] for w in WITCHES if w['id']==v), v)
        return f"Tu dois d'abord vaincre {nm}."
    return "Verrouillé."


def use_item(state, iid):
    if iid not in state["inventory"]:
        return "Tu n'as pas cet objet."
    it = ITEMS.get(iid)
    if not it or it.get("type") != "potion":
        return "Cet objet ne s'utilise pas ainsi."
    eff = it.get("effect", {})
    if "will" in eff:
        state["will"] = min(state["will_max"], state["will"] + eff["will"])
    if "grip" in eff:
        state["grip"] = max(0, state["grip"] + eff["grip"])
    if eff.get("autowin"):
        return "Garde la Braise pour un combat : utilise-la pendant l'affrontement."
    # consommer (sauf ember qui se garde pour le combat)
    if iid != "ember":
        state["inventory"].remove(iid)
    return f"{it['nom']} utilisé."
