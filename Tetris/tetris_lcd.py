"""
经典俄罗斯方块 - 复旧液晶屏版本
仿真旧式黑白液晶掌机效果：凹陷格子 + 黑色像素块
"""
import pyglet
from pyglet import shapes, text
from pyglet.window import key
import random
import os
import time as _time

# --- LCD 配色 (灰白色调，接近真实旧液晶) ---
LCD_BG       = (200, 204, 180)  # 液晶底色
LCD_CELL_BG  = (186, 190, 167)  # 空白格底色
LCD_CELL_BD  = (170, 174, 152)  # 空白格边框
LCD_ON       = (20, 22, 18)     # 活跃像素
LCD_ON_HL    = (45, 48, 38)     # 活跃像素高光
LCD_GHOST    = (158, 163, 142)  # 幽灵块
LCD_TEXT     = (50, 52, 44)     # 文字色
LCD_TEXT_DIM = (130, 134, 118)  # 淡文字
LCD_BORDER   = (60, 62, 52)     # 游戏区外框

# 方块形状
SHAPES_DEF = {
    'I': [[0,1,0,0],[0,1,0,0],[0,1,0,0],[0,1,0,0]],
    'L': [[0,1,0],[0,1,0],[0,1,1]],
    'J': [[0,1,0],[0,1,0],[1,1,0]],
    'O': [[1,1],[1,1]],
    'Z': [[1,1,0],[0,1,1],[0,0,0]],
    'S': [[0,1,1],[1,1,0],[0,0,0]],
    'T': [[0,1,0],[1,1,1],[0,0,0]],
}


class TetrisLCD(pyglet.window.Window):
    def __init__(self):
        tmp = pyglet.window.Window(100, 100, visible=False)
        self.R = tmp.get_pixel_ratio()
        tmp.close()

        # 游戏参数
        self.ROWS = 20
        self.COLS = 10
        self.GRID = 26
        self.CELL_PAD = 2

        # 布局
        self.MARGIN = 16
        self.FRAME = 3
        self.SIDEBAR = 140
        self.GAP = 12

        game_w = self.COLS * self.GRID
        game_h = self.ROWS * self.GRID
        total_w = self.MARGIN * 2 + self.FRAME * 2 + game_w + self.GAP + self.SIDEBAR
        total_h = self.MARGIN * 2 + self.FRAME * 2 + game_h

        super().__init__(
            width=total_w, height=total_h,
            caption='TETRIS',
            resizable=False
        )
        self.W = self.width; self.H = self.height

        # 物理像素
        self.G = int(self.GRID * self.R)
        self.CP = int(self.CELL_PAD * self.R)
        self.MG = int(self.MARGIN * self.R)
        self.FR = int(self.FRAME * self.R)
        self.GAME_X = self.MG + self.FR
        self.GAME_Y = self.MG + self.FR
        self.SX = self.GAME_X + self.COLS * self.G + int(self.GAP * self.R)
        self.SB_W = int(self.SIDEBAR * self.R)

        # 字体
        try: pyglet.font.add_file('/Users/robot/Library/Fonts/Sarasa-Regular.ttc')
        except: pass
        self.font_name = 'Sarasa UI SC'
        self.fs_label = int(12 * self.R)
        self.fs_value = int(18 * self.R)
        self.fs_hint = int(9 * self.R)
        self.fs_big = int(20 * self.R)

        # 批次管理
        self.bg_batch = pyglet.graphics.Batch()
        self.grid_batch = pyglet.graphics.Batch()
        self.piece_batch = pyglet.graphics.Batch()
        self.ui_batch = pyglet.graphics.Batch()
        self.overlay_batch = pyglet.graphics.Batch()

        # 手柄
        self.joysticks = []
        try:
            for js in pyglet.input.get_joysticks():
                js.open(); self.joysticks.append(js)
        except: pass

        self.DAS_DELAY = 0.180; self.ARR_DELAY = 0.040
        self.move_timers = {'left': 0, 'right': 0}
        self.move_active = {'left': False, 'right': False}
        self.LOCK_DELAY = 0.500; self.lock_timer = 0; self.is_on_ground = False
        self.gp_state = {'rot': False, 'drop': False, 'pause': False}
        self.keys_pressed = set()
        self.active_players = []
        self._load_sounds()
        self._setup_ui()
        self.reset_game()
        pyglet.clock.schedule_interval(self.update, 1 / 60.0)

    def on_close(self):
        for js in self.joysticks:
            try: js.close()
            except: pass
        super().on_close()

    def _load_sounds(self):
        snd_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sounds')
        self.sfx = {}
        for n in ['move', 'rotate', 'drop', 'clear', 'gameover', 'levelup', 'lock']:
            p = os.path.join(snd_dir, f'{n}.wav')
            if os.path.exists(p):
                try: self.sfx[n] = pyglet.media.load(p, streaming=False)
                except: pass

    def play_sfx(self, n):
        try: self.active_players = [p for p in self.active_players if p.playing]
        except: self.active_players = []
        if len(self.active_players) > 20: return
        if n in self.sfx:
            try:
                p = self.sfx[n].play()
                self.active_players.append(p)
            except: pass

    def fy(self, gy):
        return self.H - gy

    def _setup_ui(self):
        """初始化持久化 UI 元素"""
        R = self.R; G = self.G; CP = self.CP
        gaw = self.COLS * G; gah = self.ROWS * G

        # 1. 窗口背景
        self.bg_rect = shapes.Rectangle(0, 0, self.W, self.H, color=LCD_BG, batch=self.bg_batch)
        
        # 2. 游戏区外框
        fx = self.GAME_X - self.FR
        fy_top = self.GAME_Y - self.FR
        fw = gaw + self.FR * 2
        fh = gah + self.FR * 2
        self.frame_rect = shapes.Rectangle(fx, self.fy(fy_top + fh), fw, fh, color=LCD_BORDER, batch=self.bg_batch)
        self.game_inner_bg = shapes.Rectangle(self.GAME_X, self.fy(self.GAME_Y + gah), gaw, gah, color=LCD_BG, batch=self.bg_batch)

        # 3. 静态底格 (10x20)
        self.grid_cells = []
        for gy in range(self.ROWS):
            row = []
            for gx in range(self.COLS):
                px = self.GAME_X + gx * G + CP
                top = self.GAME_Y + gy * G + CP
                s = G - CP * 2
                py = self.fy(top + s)
                rect = shapes.Rectangle(px, py, s, s, color=LCD_CELL_BG, batch=self.grid_batch)
                box = shapes.Box(px, py, s, s, thickness=1, color=LCD_CELL_BD, batch=self.grid_batch)
                row.append((rect, box))
            self.grid_cells.append(row)

        # 4. 已落方块池 (10x20 对应的 ON 状态)
        self.arena_on_rects = []
        for gy in range(self.ROWS):
            row = []
            for gx in range(self.COLS):
                pixel = self._create_lcd_pixel(gx, gy, self.piece_batch)
                self._set_pixel_visible(pixel, False)
                row.append(pixel)
            self.arena_on_rects.append(row)

        # 5. 活动方块和幽灵方块池 (16个)
        self.active_pool = []
        self.ghost_pool = []
        for _ in range(16):
            p_active = self._create_lcd_pixel(0, 0, self.piece_batch)
            self._set_pixel_visible(p_active, False)
            self.active_pool.append(p_active)
            
            p_ghost = self._create_lcd_pixel(0, 0, self.piece_batch, color=LCD_GHOST)
            self._set_pixel_visible(p_ghost, False)
            self.ghost_pool.append(p_ghost)

        # 6. 侧边栏及预览区
        self._setup_sidebar_ui()

        # 7. 蒙层
        self.overlay_bg = shapes.Rectangle(0, 0, self.W, self.H, color=(*LCD_BG, 180), batch=self.overlay_batch)
        self.overlay_title = text.Label("", font_name=self.font_name, font_size=self.fs_big,
                                       weight='bold', color=(*LCD_ON, 255),
                                       x=self.W//2, y=self.H//2 + int(12*R),
                                       anchor_x='center', anchor_y='center', batch=self.overlay_batch)
        self.overlay_hint = text.Label("", font_name=self.font_name, font_size=self.fs_hint,
                                      color=(*LCD_TEXT_DIM, 255),
                                      x=self.W//2, y=self.H//2 - int(14*R),
                                      anchor_x='center', anchor_y='center', batch=self.overlay_batch)
        self.overlay_batch.visible = False

    def _create_lcd_pixel(self, gx, gy, batch, color=None, custom_rect=None):
        """创建一个 LCD 风格的像素块 (回字形组合)"""
        c = color or LCD_ON
        if custom_rect: px, py, s = custom_rect
        else:
            px = self.GAME_X + gx * self.G + self.CP
            top = self.GAME_Y + gy * self.G + self.CP
            s = self.G - self.CP * 2
            py = self.fy(top + s)
        
        rects = [shapes.Rectangle(px, py, s, s, color=c, batch=batch)]
        gap = max(1, int(s * 0.08))
        rects.append(shapes.Rectangle(px + gap, py + gap, s - gap*2, s - gap*2, color=LCD_BG, batch=batch))
        rects.append(shapes.Rectangle(px + gap*2, py + gap*2, s - gap*4, s - gap*4, color=c, batch=batch))
        return rects

    def _set_pixel_pos(self, pixel, gx, gy):
        px, top = self.GAME_X + gx * self.G + self.CP, self.GAME_Y + gy * self.G + self.CP
        s = self.G - self.CP * 2
        py = self.fy(top + s)
        if pixel[0].x != px or pixel[0].y != py:
            pixel[0].x = px; pixel[0].y = py
            gap = max(1, int(s * 0.08))
            pixel[1].x, pixel[1].y = px + gap, py + gap
            pixel[2].x, pixel[2].y = px + gap*2, py + gap*2

    def _set_pixel_visible(self, pixel, visible):
        for r in pixel:
            if r.visible != visible: r.visible = visible

    def _update_label(self, key, text_val):
        lbl = self.sidebar_labels[key]
        if lbl.text != text_val: lbl.text = text_val

    def _setup_sidebar_ui(self):
        R = self.R; sx = self.SX
        cy = self.GAME_Y + int(4 * R)
        
        self.sidebar_labels = {
            'level_title': text.Label("等级", font_name=self.font_name, font_size=self.fs_label, color=(*LCD_TEXT, 255), x=sx, y=self.fy(cy + int(12*R)), batch=self.ui_batch),
            'level_val': text.Label("1", font_name=self.font_name, font_size=self.fs_value, weight='bold', color=(*LCD_ON, 255), x=sx + self.SB_W - int(4*R), y=self.fy(cy + int(30*R)), anchor_x='right', batch=self.ui_batch),
            'score_title': text.Label("分数", font_name=self.font_name, font_size=self.fs_label, color=(*LCD_TEXT, 255), x=sx, y=self.fy(cy + int(52*R)), batch=self.ui_batch),
            'score_val': text.Label("000000", font_name=self.font_name, font_size=self.fs_value, weight='bold', color=(*LCD_ON, 255), x=sx + self.SB_W - int(4*R), y=self.fy(cy + int(70*R)), anchor_x='right', batch=self.ui_batch),
            'lines_title': text.Label("行数", font_name=self.font_name, font_size=self.fs_label, color=(*LCD_TEXT, 255), x=sx, y=self.fy(cy + int(104*R)), batch=self.ui_batch),
            'lines_val': text.Label("0", font_name=self.font_name, font_size=self.fs_value, weight='bold', color=(*LCD_ON, 255), x=sx + self.SB_W - int(4*R), y=self.fy(cy + int(122*R)), anchor_x='right', batch=self.ui_batch),
            'next_title': text.Label("下一个", font_name=self.font_name, font_size=self.fs_label, color=(*LCD_TEXT, 255), x=sx, y=self.fy(cy + int(162*R)), batch=self.ui_batch),
        }
        
        # 下一个预览池 (4x4)
        self.next_pool = []
        pcy = cy + int(182 * R)
        pG = int(20 * R); pdp = int(2 * R)
        for gy in range(4):
            row = []
            for gx in range(4):
                px = sx + gx * pG + pdp
                top = pcy + gy * pG + pdp
                s = pG - pdp * 2
                py = self.fy(top + s)
                # 预览区的底色格
                bg = shapes.Rectangle(px, py, s, s, color=LCD_CELL_BG, batch=self.ui_batch)
                bd = shapes.Box(px, py, s, s, thickness=1, color=LCD_CELL_BD, batch=self.ui_batch)
                # 预览区的 ON 像素块 (使用通用的回字逻辑)
                on_pixel = self._create_lcd_pixel(0, 0, self.ui_batch, custom_rect=(px, py, s))
                self._set_pixel_visible(on_pixel, False)
                row.append({'bg': bg, 'bd': bd, 'on': on_pixel})
            self.next_pool.append(row)
            
        # 提示
        for i, h in enumerate(["←→ 移动  ↑ 旋转", "空格 掉落  P 暂停"]):
            text.Label(h, font_name=self.font_name, font_size=self.fs_hint, color=(*LCD_TEXT_DIM, 255), x=sx, y=self.fy(cy + int(282*R) + i*int(14*R)), batch=self.ui_batch)

    # ========= 游戏逻辑 (保持不变) =========
    def reset_game(self):
        self.arena = [[0] * self.COLS for _ in range(self.ROWS)]
        self.score = 0; self.level = 1; self.lines = 0
        self.next_pt = random.choice(list(SHAPES_DEF.keys()))
        self.is_paused = self.is_game_over = False
        self.drop_counter = 0; self.drop_interval = 1.0
        self.is_on_ground = False; self.lock_timer = 0
        self.lines_to_clear, self.clear_anim_timer = [], 0
        self.player_reset()

    def player_reset(self):
        self.cur_type = self.next_pt
        self.next_pt = random.choice(list(SHAPES_DEF.keys()))
        self.cur_mat = [r[:] for r in SHAPES_DEF[self.cur_type]]
        self.pos = {'x': self.COLS // 2 - len(self.cur_mat[0]) // 2, 'y': 0}
        if self.collide(self.pos, self.cur_mat):
            self.is_game_over = True; self.play_sfx('gameover')

    def collide(self, pos, mat):
        for y, row in enumerate(mat):
            for x, v in enumerate(row):
                if v:
                    ay, ax = y + pos['y'], x + pos['x']
                    if ay >= self.ROWS or ax < 0 or ax >= self.COLS or \
                       (ay >= 0 and self.arena[ay][ax]): return True
        return False

    def merge(self):
        for y, row in enumerate(self.cur_mat):
            for x, v in enumerate(row):
                if v: self.arena[y+self.pos['y']][x+self.pos['x']] = v

    def rot_mat(self, m, d):
        nm = [[m[y][x] for y in range(len(m))] for x in range(len(m[0]))]
        if d > 0:
            for r in nm: r.reverse()
        else: nm.reverse()
        return nm

    def player_rotate(self, d):
        old = self.cur_mat
        self.cur_mat = self.rot_mat(self.cur_mat, d)
        px = self.pos['x']; off = 1
        while self.collide(self.pos, self.cur_mat):
            self.pos['x'] += off; off = -(off + (1 if off > 0 else -1))
            if abs(off) > len(self.cur_mat[0]):
                self.cur_mat = old; self.pos['x'] = px; return
        if self.is_on_ground: self.lock_timer = 0
        self.play_sfx('rotate')

    def player_drop(self):
        self.pos['y'] += 1
        if self.collide(self.pos, self.cur_mat):
            self.pos['y'] -= 1; self.is_on_ground = True
        else:
            if self.is_on_ground: self.is_on_ground = False; self.lock_timer = 0
        self.drop_counter = 0

    def lock_piece(self):
        self.merge()
        self.is_on_ground = False; self.lock_timer = 0; self.play_sfx('lock')
        self.arena_sweep()
        if not self.lines_to_clear: self.player_reset()

    def player_hard_drop(self):
        while not self.collide(self.pos, self.cur_mat): self.pos['y'] += 1
        self.pos['y'] -= 1; self.play_sfx('drop')
        self.lock_piece(); self.drop_counter = 0

    def arena_sweep(self):
        self.lines_to_clear = [y for y in range(self.ROWS) if 0 not in self.arena[y]]
        if self.lines_to_clear:
            self.play_sfx('clear')
            self.clear_anim_timer = 0.4

    def finish_clear(self):
        rc = 1
        for y in sorted(self.lines_to_clear):
            self.arena.pop(y); self.arena.insert(0, [0]*self.COLS)
            self.lines += 1; self.score += rc*100; rc *= 2
        
        if self.score >= self.level * 500:
            self.level += 1
            self.drop_interval = max(0.1, 1.0 - (self.level-1)*0.1)
            self.play_sfx('levelup')
        self.lines_to_clear = []
        self.player_reset()

    def ghost_pos(self):
        gp = {'x': self.pos['x'], 'y': self.pos['y']}
        while not self.collide(gp, self.cur_mat): gp['y'] += 1
        gp['y'] -= 1; return gp

    def move_player(self, dx):
        self.pos['x'] += dx
        if self.collide(self.pos, self.cur_mat):
            self.pos['x'] -= dx; return False
        if self.is_on_ground: self.lock_timer = 0
        self.play_sfx('move'); return True

    def on_key_press(self, sym, mod):
        self.keys_pressed.add(sym)
        if sym == key.P and not self.is_game_over: self.is_paused = not self.is_paused
        if self.is_game_over:
            if sym == key.R: self.reset_game()
            return
        if self.is_paused: return
        if sym == key.UP: self.player_rotate(1)
        elif sym == key.DOWN: self.player_drop()
        elif sym == key.SPACE: self.player_hard_drop()

    def on_key_release(self, sym, mod):
        self.keys_pressed.discard(sym)

    def handle_gamepad(self):
        if not self.joysticks: return
        js = self.joysticks[0]
        try: pp = any(b < len(js.buttons) and js.buttons[b] for b in [7,9])
        except: pp = False
        if pp:
            if not self.gp_state['pause']:
                if not self.is_game_over: self.is_paused = not self.is_paused
                self.gp_state['pause'] = True
        else: self.gp_state['pause'] = False
        if self.is_game_over:
            try:
                if any(js.buttons[b] for b in range(min(10,len(js.buttons)))): self.reset_game()
            except: pass
            return
        if self.is_paused: return
        try:
            if (hasattr(js,'y') and js.y > 0.5) or (hasattr(js,'hat_y') and js.hat_y < -0.5):
                self.player_drop()
        except: pass
        rp = False
        try: rp = any(b < len(js.buttons) and js.buttons[b] for b in [0,1,2])
        except: pass
        if rp:
            if not self.gp_state['rot']: self.player_rotate(1); self.gp_state['rot'] = True
        else: self.gp_state['rot'] = False
        hd = False
        try: hd = (hasattr(js,'hat_y') and js.hat_y > 0.5) or (len(js.buttons) > 3 and js.buttons[3])
        except: pass
        if hd:
            if not self.gp_state['drop']: self.player_hard_drop(); self.gp_state['drop'] = True
        else: self.gp_state['drop'] = False

    def update_movement(self, dt):
        if self.is_paused or self.is_game_over: return
        kl = key.LEFT in self.keys_pressed; kr = key.RIGHT in self.keys_pressed
        gl = gr = gd = False
        if self.joysticks:
            js = self.joysticks[0]
            try:
                if hasattr(js,'x'): gl = js.x < -0.5; gr = js.x > 0.5
                if hasattr(js,'y'): gd = js.y > 0.5
                if hasattr(js,'hat_x'): gl = gl or js.hat_x < -0.5; gr = gr or js.hat_x > 0.5
                if hasattr(js,'hat_y'): gd = gd or js.hat_y < -0.5
            except: pass

        for d, a, dx in [('left', kl or gl, -1), ('right', kr or gr, 1), ('down', (key.DOWN in self.keys_pressed) or gd, 0)]:
            if a:
                if d == 'down':
                    self.player_drop()
                    if self.is_on_ground: self.lock_timer += dt * 5.0 # 下推时加速锁定确认
                elif not self.move_active[d]:
                    self.move_player(dx); self.move_timers[d] = self.DAS_DELAY; self.move_active[d] = True
                else:
                    self.move_timers[d] -= dt
                    if self.move_timers[d] <= 0: self.move_player(dx); self.move_timers[d] = self.ARR_DELAY
            else: self.move_active[d] = False; self.move_timers[d] = 0

    def update(self, dt):
        if self.lines_to_clear:
            self.clear_anim_timer -= dt
            if self.clear_anim_timer <= 0: self.finish_clear()
            self._update_ui_state(); return

        self.handle_gamepad(); self.update_movement(dt)
        if not self.is_paused and not self.is_game_over:
            if self.is_on_ground:
                self.lock_timer += dt
                if self.lock_timer >= self.LOCK_DELAY: self.lock_piece()
            self.drop_counter += dt
            if self.drop_counter > self.drop_interval: self.player_drop()
        self._update_ui_state()

    # ========= 状态更新 (绘制前) =========
    def _update_ui_state(self):
        # 1. 更新 Arena
        flicker = (int(self.clear_anim_timer * 12) % 2 == 0) if self.lines_to_clear else True
        for gy, row in enumerate(self.arena):
            is_clearing = gy in self.lines_to_clear
            for gx, v in enumerate(row):
                self._set_pixel_visible(self.arena_on_rects[gy][gx], (v > 0) and (flicker or not is_clearing))
        
        # 2. 更新幽灵块
        if not self.is_game_over and not self.is_paused and not self.lines_to_clear:
            gp = self.ghost_pos()
            idx = 0
            for y, row in enumerate(self.cur_mat):
                for x, v in enumerate(row):
                    if v and idx < 16:
                        p = self.ghost_pool[idx]
                        self._set_pixel_pos(p, x + gp['x'], y + gp['y'])
                        self._set_pixel_visible(p, True)
                        idx += 1
            for i in range(idx, 16): self._set_pixel_visible(self.ghost_pool[i], False)
            
            # 3. 更新当前块
            idx = 0
            for y, row in enumerate(self.cur_mat):
                for x, v in enumerate(row):
                    if v and idx < 16:
                        p = self.active_pool[idx]
                        self._set_pixel_pos(p, x + self.pos['x'], y + self.pos['y'])
                        self._set_pixel_visible(p, True)
                        idx += 1
            for i in range(idx, 16): self._set_pixel_visible(self.active_pool[i], False)
        else:
            for p in self.ghost_pool + self.active_pool: self._set_pixel_visible(p, False)
            
        # 4. 更新侧边栏文字
        self._update_label('level_val', str(self.level))
        self._update_label('score_val', str(self.score).zfill(6))
        self._update_label('lines_val', str(self.lines))
        
        # 5. 更新下一个预览
        nm = SHAPES_DEF[self.next_pt]; ns = len(nm)
        ox, oy = (4-ns)//2, (4-ns)//2
        for gy in range(4):
            for gx in range(4):
                on = False
                if 0 <= gy - oy < ns and 0 <= gx - ox < ns:
                    on = nm[gy-oy][gx-ox] > 0
                self._set_pixel_visible(self.next_pool[gy][gx]['on'], on)

        # 6. 更新蒙层
        if self.is_paused or self.is_game_over:
            self.overlay_batch.visible = True
            ot = "游戏结束" if self.is_game_over else "已暂停"
            oh = "按 R 键重新开始" if self.is_game_over else "按 P 键继续"
            if self.overlay_title.text != ot: self.overlay_title.text = ot
            if self.overlay_hint.text != oh: self.overlay_hint.text = oh
        else:
            self.overlay_batch.visible = False

    def on_draw(self):
        self.clear()
        self.bg_batch.draw()
        self.grid_batch.draw()
        self.piece_batch.draw()
        self.ui_batch.draw()
        if self.overlay_batch.visible:
            self.overlay_batch.draw()


if __name__ == "__main__":
    game = TetrisLCD()
    pyglet.app.run()