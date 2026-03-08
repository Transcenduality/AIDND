import os, json, queue, pygame, threading, textwrap, random, time, pyttsx3
from openai import OpenAI

# -----------------------------
# 1. INITIALIZATION & PERSISTENCE
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_FILE = os.path.join(BASE_DIR, "aidnd_save.json")

pygame.init()
info = pygame.display.Info()
WIDTH, HEIGHT = int(info.current_w * 0.9), int(info.current_h * 0.9)
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("AIDND")

BG_COLOR, PANEL_COLOR = (10, 12, 16), (22, 24, 30)
ACCENT, WHITE, BORDER, GOLD_CLR = (0, 185, 255), (240, 245, 250), (60, 65, 80), (255, 215, 0)
RED_CLR, GREEN_CLR, BLUE_XP = (220, 60, 60), (60, 220, 100), (0, 120, 255)
SIDEBAR_W, BOTTOM_H = 460, 260

STAT_ORDER = [
    "Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma", 
    "Luck", "Perception", "Stealth", "Arcana", "Athletics", "Willpower", 
    "Initiative", "Speed", "Armor Class"
]

tts_muted = False 

def get_mod(val): return (val - 10) // 2

class TTSThread(threading.Thread):
    def __init__(self, text):
        super().__init__()
        self.text = text
        self.daemon = True
    def run(self):
        if tts_muted: return
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 155) 
            engine.say(self.text)
            engine.runAndWait()
        except: pass

class Hero:
    def __init__(self, name=""):
        self.name, self.pronouns = name, "They/Them"
        self.level, self.xp, self.money = 1, 0, 0
        self.stats = {s: 10 for s in STAT_ORDER}
        self.armor, self.inventory = "None", []
        self.suggested_stat = "Luck"
        self.pending_roll = self.raw_die = None
        self.hp = self.max_hp = 20
        self.update_max_hp()
        self.hp = self.max_hp

    def to_dict(self): return self.__dict__
    
    @staticmethod
    def from_dict(d):
        h = Hero(); h.__dict__.update(d); h.update_max_hp(); return h

    def update_max_hp(self):
        con_mod = get_mod(self.stats.get("Constitution", 10))
        self.max_hp = 15 + (self.level * 5) + (con_mod * self.level)
        if self.hp > self.max_hp: self.hp = self.max_hp

    def add_xp(self, amount):
        if self.level >= 100: return
        self.xp += amount
        while self.xp >= (self.level * 100) and self.level < 100:
            self.xp -= (self.level * 100); self.level += 1
            self.update_max_hp(); self.hp = self.max_hp 

def save_game(world, players, chat):
    try:
        data = {"world": world, "players": {k: v.to_dict() for k, v in players.items()}, "chat": chat[-50:]}
        with open(SAVE_FILE, "w") as f: json.dump(data, f, indent=4)
    except: pass

class InputBox:
    def __init__(self, label, text="", multiline=False):
        self.label, self.text, self.multiline, self.rect, self.active = label, str(text), multiline, pygame.Rect(0,0,0,0), False
        self.box_scroll = 0
    def handle(self, event, mx, my):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
        if self.active:
            if event.type == pygame.MOUSEWHEEL and self.rect.collidepoint(mx, my):
                self.box_scroll = max(0, self.box_scroll - event.y * 30); return True 
            elif event.type == pygame.TEXTINPUT: self.text += event.text
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE: self.text = self.text[:-1]
        return False
    def draw(self, surf, x, y, w, f, sf, locked=False):
        wrapped = textwrap.wrap(str(self.text), width=int(w/9.5)) or [""]
        box_h = min(120, max(60, len(wrapped) * 25 + 30)) if self.multiline else 60
        self.rect = pygame.Rect(x, y, w, box_h)
        pygame.draw.rect(surf, PANEL_COLOR if not locked else (30,30,35), self.rect, border_radius=8)
        pygame.draw.rect(surf, ACCENT if (self.active and not locked) else BORDER, self.rect, 2, border_radius=8)
        surf.blit(sf.render(self.label, True, ACCENT if (self.active and not locked) else (120, 120, 120)), (x, y - 25))
        old_clip = surf.get_clip(); surf.set_clip(self.rect.inflate(-10, -10))
        for i, line in enumerate(wrapped):
            ty = y + 10 + (i * 25) - self.box_scroll
            if ty > y - 20 and ty < y + box_h: surf.blit(f.render(line, True, WHITE), (x+12, ty))
        surf.set_clip(old_clip); return box_h

def ai_thread(client, sys_msg, history, out_q, msg_type):
    try:
        msgs = [{"role": "system", "content": sys_msg}] + [{"role": "user" if m["role"]=="Player" else "assistant", "content": m["content"]} for m in history[-12:]]
        res = client.chat.completions.create(model="gpt-4o", messages=msgs, response_format={"type": "json_object"})
        out_q.put({"type": msg_type, "data": json.loads(res.choices[0].message.content)})
    except Exception as e: out_q.put({"type": "ERROR", "data": str(e)})

def main():
    global tts_muted
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if api_key else None
    clock = pygame.time.Clock()
    fonts = {"title": pygame.font.SysFont("Georgia", 24, bold=True), "reg": pygame.font.SysFont("Verdana", 13), "small": pygame.font.SysFont("Verdana", 9, bold=True), "bold": pygame.font.SysFont("Verdana", 11, bold=True)}
    
    # MODIFIED: world_data now includes 'history_summary'
    game_state, world_data, chat_log = "SETUP_WORLD", {"name": "", "desc": "", "history_summary": "The journey has just begun."}, []
    players = {"P1": Hero("Hero 1"), "P2": Hero("Hero 2")}
    chat_scroll, total_chat_h, roll_timer_start = 0, 0, None
    turn_counter = 0 # Track turns for chronicle updates

    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, "r") as f:
                d = json.load(f); world_data = d["world"]; chat_log = d["chat"]
                for k, v in d["players"].items(): players[k] = Hero.from_dict(v)
                game_state = "PLAY"
        except: pass

    boxes = {"w": InputBox("World Name", ""), "d": InputBox("Setting", "", True), "p1": InputBox("P1 Name", ""), "p2": InputBox("P2 Name", ""), "a1": InputBox("P1 Action", "", True), "a2": InputBox("P2 Action", "", True)}
    ai_q, ai_thinking, roll_phase, current_setup = queue.Queue(), False, False, "P1"

    while True:
        screen.fill(BG_COLOR)
        mx, my = pygame.mouse.get_pos(); events = pygame.event.get(); click = False
        for e in events:
            if e.type == pygame.QUIT: return
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1: click = True
            
            if game_state == "PLAY":
                boxes["a1"].handle(e, mx, my); boxes["a2"].handle(e, mx, my)
                if e.type == pygame.MOUSEWHEEL:
                    chat_scroll = max(0, chat_scroll - e.y * 45)
            elif game_state == "SETUP_WORLD": boxes["w"].handle(e, mx, my); boxes["d"].handle(e, mx, my)
            elif game_state == "SETUP_NAMES": boxes["p1"].handle(e, mx, my); boxes["p2"].handle(e, mx, my)

            if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
                if game_state == "PLAY" and not ai_thinking and not roll_phase:
                    p1_text = boxes["a1"].text.strip() or "I wait."
                    p2_text = boxes["a2"].text.strip() or "I wait."
                    chat_log.append({"role": "Player", "content": f"{players['P1'].name}: {p1_text}"})
                    chat_log.append({"role": "Player", "content": f"{players['P2'].name}: {p2_text}"})
                    boxes["a1"].text = boxes["a2"].text = ""
                    ai_thinking = True
                    sys = f"Pick ONE relevant stat for P1/P2 from {STAT_ORDER}. Return JSON: {{\"p1_stat\":\"\", \"p2_stat\":\"\"}}"
                    threading.Thread(target=ai_thread, args=(client, sys, chat_log, ai_q, "STATS")).start()
                elif game_state == "SETUP_WORLD" and boxes["w"].text:
                    world_data["name"], world_data["desc"] = boxes["w"].text, boxes["d"].text
                    game_state = "SETUP_NAMES"
                elif game_state == "SETUP_NAMES" and boxes["p1"].text:
                    players["P1"].name, players["P2"].name = boxes["p1"].text, boxes["p2"].text
                    game_state = "SETUP_PRONOUNS"

        if game_state == "SETUP_WORLD":
            boxes["w"].draw(screen, WIDTH//4, 160, WIDTH//2, fonts["reg"], fonts["small"])
            boxes["d"].draw(screen, WIDTH//4, 320, WIDTH//2, fonts["reg"], fonts["small"])
        elif game_state == "SETUP_NAMES":
            boxes["p1"].draw(screen, WIDTH//4, 160, WIDTH//2, fonts["reg"], fonts["small"])
            boxes["p2"].draw(screen, WIDTH//4, 320, WIDTH//2, fonts["reg"], fonts["small"])
        elif game_state == "SETUP_PRONOUNS":
            screen.blit(fonts["title"].render(f"Pronouns: {players[current_setup].name}", True, GOLD_CLR), (WIDTH//2-100, 100))
            for i, opt in enumerate(["He/Him", "She/Her", "They/Them"]):
                btn = pygame.Rect(WIDTH//2-100, 180+(i*60), 200, 45)
                pygame.draw.rect(screen, PANEL_COLOR, btn, border_radius=8)
                pygame.draw.rect(screen, ACCENT if btn.collidepoint(mx, my) else BORDER, btn, 2, border_radius=8)
                screen.blit(fonts["reg"].render(opt, True, WHITE), (btn.x+55, btn.y+12))
                if click and btn.collidepoint(mx, my):
                    players[current_setup].pronouns = opt
                    if current_setup == "P1": current_setup = "P2"
                    else: game_state = "SETUP_STATS"; current_setup = "P1"
        elif game_state == "SETUP_STATS":
            screen.blit(fonts["title"].render(f"Draft Primary Skill: {players[current_setup].name}", True, GOLD_CLR), (WIDTH//2 - 200, 50))
            for idx, s in enumerate(STAT_ORDER):
                sx, sy = WIDTH//4 + (idx%3 * 220), 150 + (idx//3 * 50)
                btn = pygame.Rect(sx, sy, 200, 40)
                pygame.draw.rect(screen, PANEL_COLOR, btn, border_radius=8)
                pygame.draw.rect(screen, ACCENT if btn.collidepoint(mx, my) else BORDER, btn, 2, border_radius=8)
                screen.blit(fonts["reg"].render(s, True, WHITE), (sx+15, sy+10))
                if click and btn.collidepoint(mx, my):
                    players[current_setup].stats = {st: random.randint(8, 14) for st in STAT_ORDER}
                    players[current_setup].stats[s] = 16
                    players[current_setup].update_max_hp(); players[current_setup].hp = players[current_setup].max_hp
                    if current_setup == "P1": current_setup = "P2"
                    else: game_state = "PLAY"; save_game(world_data, players, chat_log)

        elif game_state == "PLAY":
            chat_rect = pygame.Rect(40, 40, WIDTH-SIDEBAR_W-80, HEIGHT-BOTTOM_H-80)
            
            current_y_offset = 0
            for m in chat_log:
                col, prefix = (ACCENT, "DM: ") if m["role"] == "DM" else (WHITE, "")
                txt = prefix + str(m["content"])
                lines = textwrap.wrap(txt, width=int(chat_rect.w/8.5))
                
                for l in lines:
                    draw_y = chat_rect.y + current_y_offset - chat_scroll
                    if chat_rect.y <= draw_y <= chat_rect.y + chat_rect.h - 20:
                        screen.blit(fonts["reg"].render(l, True, col), (chat_rect.x, draw_y))
                    current_y_offset += 25
                current_y_offset += 15
            
            total_chat_h = current_y_offset
            chat_scroll = max(0, min(chat_scroll, total_chat_h - chat_rect.h + 50))

            pygame.draw.rect(screen, PANEL_COLOR, (WIDTH-SIDEBAR_W, 0, SIDEBAR_W, HEIGHT))
            for i, pk in enumerate(["P1", "P2"]):
                p, py = players[pk], i * (HEIGHT // 2) + 20
                screen.blit(fonts["title"].render(f"{p.name} ({p.pronouns})", True, ACCENT), (WIDTH-SIDEBAR_W+20, py))
                pygame.draw.rect(screen, (40, 40, 45), (WIDTH-SIDEBAR_W+20, py+35, 200, 10))
                pygame.draw.rect(screen, RED_CLR, (WIDTH-SIDEBAR_W+20, py+35, int((p.hp/p.max_hp)*200), 10))
                txp = p.level * 100
                pygame.draw.rect(screen, (40, 40, 45), (WIDTH-SIDEBAR_W+20, py+50, 200, 6))
                pygame.draw.rect(screen, BLUE_XP, (WIDTH-SIDEBAR_W+20, py+50, int((p.xp/txp)*200), 6))
                screen.blit(fonts["small"].render(f"Lv.{p.level} | HP:{p.hp}/{p.max_hp} | XP:{p.xp}/{txp} | Gold: {p.money}", True, WHITE), (WIDTH-SIDEBAR_W+20, py+60))
                screen.blit(fonts["small"].render(f"Armor: {p.armor}", True, GOLD_CLR), (WIDTH-SIDEBAR_W+20, py+78))
                inv_w = textwrap.wrap(f"Items: {', '.join(p.inventory) or 'None'}", width=45)
                for j, ln in enumerate(inv_w): screen.blit(fonts["small"].render(ln, True, WHITE), (WIDTH-SIDEBAR_W+20, py+92+(j*12)))
                for idx, s in enumerate(STAT_ORDER):
                    screen.blit(fonts["small"].render(f"{s}: {p.stats[s]}", True, (170,170,170)), (WIDTH-SIDEBAR_W+20+(idx%2*220), py+135+(idx//2*14)))

            boxes["a1"].draw(screen, 20, HEIGHT-210, (WIDTH-SIDEBAR_W)//2-40, fonts["reg"], fonts["small"], roll_phase or ai_thinking)
            boxes["a2"].draw(screen, (WIDTH-SIDEBAR_W)//2+20, HEIGHT-210, (WIDTH-SIDEBAR_W)//2-40, fonts["reg"], fonts["small"], roll_phase or ai_thinking)

            mute_btn = pygame.Rect(WIDTH-SIDEBAR_W-100, HEIGHT-50, 80, 30)
            pygame.draw.rect(screen, (40,40,45), mute_btn, border_radius=5)
            pygame.draw.rect(screen, RED_CLR if tts_muted else GREEN_CLR, mute_btn, 2, border_radius=5)
            screen.blit(fonts["small"].render("MUTE" if not tts_muted else "MUTED", True, WHITE), (mute_btn.x+15, mute_btn.y+8))
            if click and mute_btn.collidepoint(mx, my): tts_muted = not tts_muted

            if roll_phase:
                for i, pk in enumerate(["P1", "P2"]):
                    bx = 20 if pk == "P1" else (WIDTH-SIDEBAR_W)//2 + 20
                    btn, p = pygame.Rect(bx, HEIGHT - 70, 240, 45), players[pk]
                    if p.pending_roll is None:
                        pygame.draw.rect(screen, ACCENT, btn, 2, border_radius=8)
                        screen.blit(fonts["bold"].render(f"Roll {p.suggested_stat}", True, WHITE), (btn.x+15, btn.y+12))
                        if click and btn.collidepoint(mx, my):
                            safe_stat = p.suggested_stat if p.suggested_stat in p.stats else "Luck"
                            p.raw_die = random.randint(1, 20)
                            p.pending_roll = p.raw_die + get_mod(p.stats[safe_stat])
                            if players["P1" if pk=="P2" else "P2"].pending_roll is not None: roll_timer_start = time.time()
                    else:
                        res_col = RED_CLR if p.pending_roll < 10 else (GOLD_CLR if p.pending_roll < 15 else GREEN_CLR)
                        pygame.draw.rect(screen, res_col, btn, 2, border_radius=8)
                        safe_stat = p.suggested_stat if p.suggested_stat in p.stats else "Luck"
                        m = get_mod(p.stats[safe_stat])
                        screen.blit(fonts["bold"].render(f"{p.raw_die} {'+' if m>=0 else ''}{m} = {p.pending_roll}", True, res_col), (btn.x+15, btn.y+12))

                if roll_timer_start and time.time() - roll_timer_start > 2.0:
                    ai_thinking, roll_phase, roll_timer_start = True, False, None
                    # MODIFIED: System prompt now injects world history summary
                    sys = (f"""Role: Professional DM for {world_data['name']}.
                    History So Far: {world_data['history_summary']}
                    Narrate briefly (max 3 sentences) for P1 ({players['P1'].name}, {players['P1'].pronouns}) and P2 ({players['P2'].name}, {players['P2'].pronouns}). Use rolls (P1:{players['P1'].pending_roll}, P2:{players['P2'].pending_roll}).
                    If a player gains or loses hp, the change must be included in their hp_delta.
                    If a player gains xp, the change must be included in their xp_gain.
                    If a player gains or spends/loses money, the change must be included in their money_delta.
                    If a player loses or gains an item, the change must be included in their inv_delta.
                    If a player removes or equips an armor piece, the change must be included in their armor_delta.
                    If a player improves in a specific attribute, the change must be included in their stat_mod.
                    Only remove or add health if the situation clearly justifies it, otherwise use a hp_delta of 0.
                    If an item name changes, - the old item name and + the new item name to the same player's inv_delta.

                    Your narrative prose must be in plain text, never referencing rolls, attributes, or including information in brackets.
                           
                    ### JSON INSTRUCTION SET:
                    - "p1_hp_delta": Integer (-5, 10)
                    - "p1_xp_gain": Integer (25)
                    - "p1_money_delta": Integer (50, -20)
                    - "p1_inv_delta": List (["+ Sword", "- Rations"])
                    - "p1_armor_delta": String ("+ Plate Armor", "- Plate Armor")
                    - "p1_stat_mod": Object ({{"Strength": 1}})

                    RESPONSE TEMPLATE:
                    {{ "text": "Narrative...", "p1_hp_delta":0, "p1_xp_gain":20, "p1_money_delta":0, "p1_inv_delta":[], "p1_armor_delta":"", "p1_stat_mod":{{}},
                       "p2_hp_delta":0, "p2_xp_gain":20, "p2_money_delta":0, "p2_inv_delta":[], "p2_armor_delta":"", "p2_stat_mod":{{}} }}""")
                    threading.Thread(target=ai_thread, args=(client, sys, chat_log, ai_q, "NARRATIVE")).start()

        try:
            msg = ai_q.get_nowait()
            if msg["type"] == "STATS":
                p1_s = msg["data"].get("p1_stat", "Luck")
                p2_s = msg["data"].get("p2_stat", "Luck")
                players["P1"].suggested_stat = p1_s if p1_s in STAT_ORDER else "Luck"
                players["P2"].suggested_stat = p2_s if p2_s in STAT_ORDER else "Luck"
                players["P1"].pending_roll = players["P2"].pending_roll = None
                ai_thinking, roll_phase = False, True
            elif msg["type"] == "NARRATIVE":
                res = msg["data"]; chat_log.append({"role": "DM", "content": res["text"]}); TTSThread(res["text"]).start()
                for pk in ["P1", "P2"]:
                    p = players[pk]
                    hp_change = res.get(f"{pk.lower()}_hp_delta", 0)
                    if hp_change < 0 and p.pending_roll and p.pending_roll >= 5:
                        hp_change = max(hp_change, -int(p.max_hp * 0.15))
                    p.hp = max(0, min(p.max_hp, p.hp + hp_change))
                    p.add_xp(res.get(f"{pk.lower()}_xp_gain", 0))
                    p.money = max(0, p.money + res.get(f"{pk.lower()}_money_delta", 0))
                    for st, val in res.get(f"{pk.lower()}_stat_mod", {}).items():
                        if st in p.stats: p.stats[st] = max(1, min(20, p.stats[st] + val))
                    arm = res.get(f"{pk.lower()}_armor_delta", "")
                    if arm and arm.startswith("+"): p.armor = arm[1:].strip()
                    elif arm and arm.startswith("-"): p.armor = "None"
                    for itm in res.get(f"{pk.lower()}_inv_delta", []):
                        clean_item = itm[1:].strip()
                        if itm.startswith("+") and clean_item not in p.inventory: p.inventory.append(clean_item)
                        elif itm.startswith("-") and clean_item in p.inventory: p.inventory.remove(clean_item)
                            
                ai_thinking = False; chat_scroll = total_chat_h
                turn_counter += 1
                
                # CHRONICLE UPDATE: Trigger every 3 turns
                if turn_counter >= 3:
                    turn_counter = 0
                    chron_sys = f"""Update the 'History Summary' below by incorporating the recent events. 
                    Keep the summary cohesive and under 200 words. Focus on major plot points, locations, and NPC status.
                    Current Summary: {world_data['history_summary']}
                    Recent Events: {json.dumps(chat_log[-6:])}
                    Return JSON: {{"new_history": "..."}}"""
                    threading.Thread(target=ai_thread, args=(client, chron_sys, [], ai_q, "CHRONICLE")).start()
                
                save_game(world_data, players, chat_log)

            elif msg["type"] == "CHRONICLE":
                world_data["history_summary"] = msg["data"].get("new_history", world_data["history_summary"])
                save_game(world_data, players, chat_log)

        except queue.Empty: pass

        if ai_thinking: pygame.draw.circle(screen, ACCENT, (WIDTH-40, 40), 10)
        pygame.display.flip(); clock.tick(60)


if __name__ == "__main__": main()
