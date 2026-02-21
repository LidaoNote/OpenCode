"""
经典俄罗斯方块 - 极致调教版
- Retina HiDPI 适配 & OrderedGroup 层级管理
- 全局粒子池 & 模块化输入 + 合成音效
"""
import os
import sys
import random
import math
import io
import struct
import wave
import time

# === 隐藏 macOS 系统冗余打印 (必须在 import pyglet 之前执行) ===
os.environ['APPLE_PERSISTENCE_IGNORE_STATE'] = 'YES'

# === 启动信息已静默 ===

import pyglet
from pyglet import shapes, text, clock
from pyglet.window import key

# === 游戏常量 ===
GRID_SIZE = 24
GAME_ROWS = 30
GAME_COLS = 14
SIDEBAR_WIDTH = 200
PADDING = 20

# 全局粒子限制（防止内存泄漏）
MAX_PARTICLES = 1000

# AI 战术与评分权重系统 (遗传算法 10 代进化最优参数 G8 - Tetris 率 99.2%)
AI_SEARCH_LIMIT = 8                # AI 搜索时选取的精英候选数量
AI_TETRIS_REWARD = 12497569.0      # 消四行的战略级奖励
AI_I_PIECE_WASTE_PENALTY = 77260651.0 # 浪费竖条的核威慑级罚金
AI_WELL_ABUSE_PENALTY = 16883362.0 # 随地填井的战略级罚金
AI_MELTDOWN_PENALTY = 232666924.0  # 井位堵死的毁灭级惩罚
AI_HOLE_PENALTY = 76474473.0       # 地基空洞的重罚基数
AI_BLOCK_COVER_PENALTY = 11041287.0# 遮盖空洞的严厉惩罚
AI_BUMPINESS_PENALTY = 63246.0     # 地基平整度惩罚
AI_ROW_TRANSITION_PENALTY = 33910.0# 行边界转换惩罚
AI_COL_TRANSITION_PENALTY = 29216.0# 列边界转换惩罚
AI_HEIGHT_PENALTY = 1275.0         # 堆叠总高度惩罚
AI_MAX_HEIGHT_PENALTY = 5205.0     # 堆叠峰值高度惩罚
AI_LANDING_PENALTY = 313.0         # 落地位置过高的惩罚
AI_ROW_INTEGRITY_FACTOR = 2440.0   # 满行程度的激励系数
AI_SKYSCRAPER_PENALTY = 3776817.0  # 强制削减 13 列摩天楼

# 资源配置
FONT_PATH = "fonts/Sarasa-Regular.ttc" # 优先使用的字体路径
SFX_FILENAME = "sfx.wav"               # 内存生成的临时音效文件名

# 系统动力学参数
DAS_DELAY = 0.180  # 自动重复延迟 (延迟自动重复)
ARR_DELAY = 0.040  # 自动重复速率 (自动重复速率)
LOCK_DELAY_LIMIT = 0.500  # 方块落地后的锁定缓冲时间
# 颜色定义
COLORS = [
    (0, 0, 0),           # 0: 背景
    (239, 68, 68),       # 1: Z (Red)
    (34, 197, 94),       # 2: S (Green)
    (59, 130, 246),      # 3: T (Blue)
    (234, 179, 8),       # 4: O (Yellow)
    (236, 72, 153),      # 5: L (Pink)
    (6, 182, 212),       # 6: I (Cyan)
    (249, 115, 22),      # 7: J (Orange)
]

BG_COLOR = (15, 23, 42)
CARD_BG = (30, 41, 59)
TEXT_COLOR = (248, 250, 252)
PRIMARY_COLOR = (59, 130, 246)
TEXT_GREY = (161, 161, 170)

# 方块形状定义
SHAPES = {
    'I': [[0,6,0,0],[0,6,0,0],[0,6,0,0],[0,6,0,0]],
    'L': [[0,5,0],[0,5,0],[0,5,5]],
    'J': [[0,7,0],[0,7,0],[7,7,0]],
    'O': [[4,4],[4,4]],
    'Z': [[1,1,0],[0,1,1],[0,0,0]],
    'S': [[0,2,2],[2,2,0],[0,0,0]],
    'T': [[0,3,0],[3,3,3],[0,0,0]],
}


class Particle:
    """粒子效果类 - 用于消行爆炸动画"""
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.color = color
        self.vx = (random.random() - 0.5) * 10
        self.vy = (random.random() - 0.5) * 10 + 2
        self.alpha = 255
        self.gravity = 0.2
        self.size = random.randint(2, 5)
        self.age = 0.0          # 记录生存时长
        self.max_age = 1.5      # 强制生存上限 (1.5秒)

    def update(self, dt):
        """更新粒子状态，返回是否仍然存活"""
        self.vx *= 0.98
        self.vy -= self.gravity
        self.x += self.vx
        self.y += self.vy
        self.alpha -= 300 * dt
        self.age += dt
        
        # 双重保险：alpha 耗尽 或 达到最大生存时间
        return self.alpha > 0 and self.age < self.max_age


class InputHandler:
    """输入处理器 - 统一管理键盘和手柄输入"""
    
    def __init__(self):
        # 键盘状态
        self.keys_pressed = set()
        self.key_latches = set()
        
        # 手柄状态
        self.gamepad_latches = {}
        self.gamepad_counters = {}
        
        # DAS/ARR 系统
        self.move_timers = {'left': 0, 'right': 0}
        self.move_active = {'left': False, 'right': False}
    
    def update_move_timers(self, dt):
        for direction in self.move_timers:
            if self.move_active[direction]:
                self.move_timers[direction] -= dt
    
    def check_gamepad_trigger(self, joystick, buttons, axis_config=None):
        """检查手柄按键触发（边沿检测与防抖）"""
        is_pressed = False
        try:
            is_pressed = any(b < len(joystick.buttons) and joystick.buttons[b] for b in buttons)
            if not is_pressed and axis_config:
                axis_name, threshold, greater_than = axis_config
                axis_value = getattr(joystick, axis_name, 0)
                is_pressed = (axis_value > threshold) if greater_than else (axis_value < threshold)
        except Exception as e:
            print(f"[!] Warning: Gamepad state detection error: {e}")
        
        # 生成按键组的唯一标识
        button_id = tuple(sorted(buttons)) + (axis_config or ())
        
        last_state = self.gamepad_latches.get(button_id, False)
        counter = self.gamepad_counters.get(button_id, 0)
        
        triggered = False
        if is_pressed:
            if not last_state:  # 刚按下（上升沿）
                triggered = True
                self.gamepad_latches[button_id] = True
                self.gamepad_counters[button_id] = 0
        else:
            # 必须连续 5 帧检测到 False 才解锁（防抖）
            if counter > 5:
                self.gamepad_latches[button_id] = False
            else:
                self.gamepad_counters[button_id] = counter + 1
        
        return triggered


class TetrisGame(pyglet.window.Window):
    """俄罗斯方块主游戏类"""
    
    def __init__(self):
        """初始化游戏窗口与核心状态"""
        self.pixel_ratio = self._detect_pixel_ratio()
        R = self.pixel_ratio
        
        # 窗口布局参数
        win_w = int(GAME_COLS * GRID_SIZE + SIDEBAR_WIDTH + PADDING * 2)
        win_h = int(GAME_ROWS * GRID_SIZE + PADDING * 2)
        super().__init__(width=win_w, height=win_h, caption='经典俄罗斯方块 | Modern Tetris')
        
        self.physical_width, self.physical_height = self.width, self.height
        self.grid_size = int(GRID_SIZE * R)
        self.padding = int(PADDING * R)
        self.sidebar_width = int(SIDEBAR_WIDTH * R)
        
        # 游戏状态
        self.selected_level = 1
        self.hold_enabled = False
        self.ui_time = 0.0
        self.reset_hold_timer = 0.0
        self.is_paused = False
        self.is_game_over = True
        self.idle_timer = 0.0
        self.idle_threshold = 15.0
        
        # AI 演示状态
        self.demo_mode = False
        self.demo_target_score = 0
        self.demo_ai_delay = 0.0
        self.demo_ai_action = None
        self.demo_ai_step = 0
        self.demo_ai_target_info = None
        self.ai_conservative_mode = False
        
        # 输入与资源初始化
        self.input_handler = InputHandler()
        self.joysticks = self._initialize_joysticks()
        
        self._initialize_fonts()
        self._initialize_audio()
        self._initialize_graphics()
        
        self.reset_game(self.selected_level)
        self.is_game_over = True
        pyglet.clock.schedule_interval(self.update, 1.0 / 60.0)
    
    def _detect_pixel_ratio(self):
        try:
            temp = pyglet.window.Window(visible=False)
            ratio = temp.get_pixel_ratio()
            temp.close()
            return ratio
        except Exception as e:
            print(f"[!] Rendering scale fallback: {e}")
            return 1.0
    
    def _initialize_joysticks(self):
        joysticks = []
        try:
            for joystick in pyglet.input.get_joysticks():
                joystick.open(); joysticks.append(joystick)
        except Exception as e:
            print(f"[!] Warning: Joystick initialization error: {e}")
        return joysticks
    
    def _initialize_fonts(self):
        """初始化游戏字体系统"""
        self.font_name = 'sans-serif'
        try:
            # 优先从资源目录加载自定义字体
            if os.path.exists(FONT_PATH):
                pyglet.font.add_file(FONT_PATH)
                self.font_name = 'Sarasa UI SC'
            else:
                pass # 字体缺失静默处理
        except Exception as e:
            print(f"[!] Warning: Font system initialization error: {e}")

        R = self.pixel_ratio
        self.font_size_large, self.font_size_main = int(28*R), int(20*R)
        self.font_size_small, self.font_size_hint = int(11*R), int(10*R)
    
    def _initialize_audio(self):
        self.sound_effects, self.active_sound_players = {}, []
        self._generate_sound_effects()
    
    def _generate_sound_effects(self):
        sample_rate = 44100
        sound_defs = {
            'move': [(1319, 0.035, 0.15)],
            'rotate': [(523, 0.035, 0.2), (784, 0.045, 0.22)],
            'lock': [(131, 0.05, 0.2)],
            'drop': [('sweep', 784, 131, 0.08, 0.25)],
            'clear': [(523, 0.06, 0.22), (659, 0.06, 0.22), (784, 0.06, 0.24), (1047, 0.12, 0.26)],
            'levelup': [(523, 0.08, 0.2), (0, 0.015, 0), (587, 0.08, 0.2), (0, 0.015, 0), (659, 0.08, 0.22), (0, 0.015, 0), (784, 0.08, 0.22), (0, 0.015, 0), (1047, 0.16, 0.25)],
            'gameover': [(659, 0.22, 0.2), (0, 0.04, 0), (523, 0.22, 0.18), (0, 0.04, 0), (440, 0.22, 0.16), (0, 0.04, 0), (330, 0.4, 0.18)]
        }
        for n, notes in sound_defs.items():
            samples = self._synthesize_notes(notes, sample_rate)
            self.sound_effects[n] = pyglet.media.load(SFX_FILENAME, file=self._create_wav_buffer(samples, sample_rate), streaming=False)
    
    def _synthesize_notes(self, notes, sample_rate):
        samples = []
        
        for note in notes:
            if note[0] == 'sweep':
                # 扫频音效: ('sweep', f_start, f_end, dur, vol, [buzz])
                kind, freq_start, freq_end, duration, volume = note[:5]
                buzz = note[5] if len(note) > 5 else 0.0 # 0.0(软) - 1.0(硬/方波)
                num_samples = int(sample_rate * duration)
                
                for i in range(num_samples):
                    progress = i / max(1, num_samples)
                    frequency = freq_start + (freq_end - freq_start) * progress
                    value = self._oscillator(frequency, i / sample_rate, volume, buzz)
                    envelope = self._adsr_envelope(i, num_samples, sample_rate, 0.003, 0.01, 0.6, duration * 0.2)
                    samples.append(int(value * envelope * 32767))
            else:
                # 普通音符: (freq, dur, vol, [buzz])
                frequency, duration, volume = note[:3]
                buzz = note[3] if len(note) > 3 else 0.0
                num_samples = int(sample_rate * duration)
                
                if frequency == 0:
                    samples.extend([0] * num_samples)
                else:
                    for i in range(num_samples):
                        value = self._oscillator(frequency, i / sample_rate, volume, buzz)
                        envelope = self._adsr_envelope(i, num_samples, sample_rate, 0.005, 0.02, 0.5, duration * 0.25)
                        samples.append(int(value * envelope * 32767))
        
        return samples

    def _oscillator(self, frequency, time, volume, buzz=0.0):
        """振荡器：正弦/三角/方波/噪声混合"""
        # buzz > 1.5 模式：输出物理白噪声，用于模拟破碎、打击感
        if buzz > 1.5:
            return (random.random() * 2 - 1) * volume
            
        if frequency <= 0: return 0.0
        
        phase = (time * frequency) % 1.0
        # 基础音色
        sine = math.sin(2 * math.pi * frequency * time)
        triangle = 4 * abs(phase - 0.5) - 1
        
        # 8-bit 方波
        square = 1.0 if phase < 0.5 else -1.0
        
        # 混合逻辑
        base = (sine * 0.7 + triangle * 0.3)
        return (base * (1.0 - buzz) + square * buzz) * volume
    
    def _adsr_envelope(self, sample_index, total_samples, sample_rate, attack, decay, sustain, release):
        time = sample_index / sample_rate
        total_time = total_samples / sample_rate
        release_start = total_time - release
        
        if time < attack:
            return time / attack  # Attack
        elif time < attack + decay:
            return 1.0 - (1.0 - sustain) * ((time - attack) / decay)  # Decay
        elif time < release_start:
            return sustain  # Sustain
        else:
            return sustain * max(0, (total_time - time) / release)  # Release
    
    def _create_wav_buffer(self, samples, sample_rate):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(sample_rate)
            f.writeframes(struct.pack(f'<{len(samples)}h', *samples))
        buffer.seek(0); return buffer
    
    def play_sound(self, sound_name):
        """播放音效 (带自动清理和并发限制)"""
        try:
            self.active_sound_players = [p for p in self.active_sound_players if p.playing]
        except Exception as e:
            print(f"[!] Sound engine init error: {e}")
            self.active_sound_players = []
        
        # 限制最大同时播放数量，防止内存泄漏
        if len(self.active_sound_players) >= 50:
            return
        
        if sound_name in self.sound_effects:
            try:
                player = self.sound_effects[sound_name].play()
                self.active_sound_players.append(player)
            except Exception as e:
                print(f"[!] Warning: Sound play instance error: {e}")
    
    def _initialize_graphics(self):
        # 创建渲染批次
        self.batch_background = pyglet.graphics.Batch()
        self.batch_grid = pyglet.graphics.Batch()
        self.batch_arena = pyglet.graphics.Batch()
        self.batch_active_piece = pyglet.graphics.Batch()
        self.batch_ui = pyglet.graphics.Batch()
        self.batch_particles = pyglet.graphics.Batch()
        self.batch_overlay = pyglet.graphics.Batch()
        
        self.ui_group_background = pyglet.graphics.Group(order=0)
        self.ui_group_foreground = pyglet.graphics.Group(order=1)
        self._create_ui_elements()
    
    def _create_ui_elements(self):
        G = self.grid_size
        P = self.padding
        R = self.pixel_ratio
        
        game_area_width = GAME_COLS * G
        game_area_height = GAME_ROWS * G
        
        # === 背景层 ===
        self.background = shapes.Rectangle(
            0, 0, self.physical_width, self.physical_height,
            color=BG_COLOR, batch=self.batch_background
        )
        
        self.game_area_frame = shapes.BorderedRectangle(
            P - 10, self.flip_y(P + game_area_height + 10),
            game_area_width + 20, game_area_height + 20,
            border=1, color=BG_COLOR, border_color=(63, 63, 70),
            batch=self.batch_background
        )
        
        self.game_area_background = shapes.Rectangle(
            P, self.flip_y(P + game_area_height),
            game_area_width, game_area_height,
            color=(2, 4, 10), batch=self.batch_background
        )
        
        self.grid_lines = []
        for x in range(GAME_COLS + 1):
            px = P + x * G
            self.grid_lines.append(shapes.Line(px, self.flip_y(P), px, self.flip_y(P + game_area_height), color=(35,45,65), batch=self.batch_grid))
        for y in range(GAME_ROWS + 1):
            py = self.flip_y(P + y * G)
            self.grid_lines.append(shapes.Line(P, py, P + game_area_width, py, color=(35,45,65), batch=self.batch_grid))
        
        # === 游戏区方块池 ===
        self.arena_rectangles = []
        self.arena_borders = []
        
        for y in range(GAME_ROWS):
            row_rects = []
            row_borders = []
            for x in range(GAME_COLS):
                rect = shapes.Rectangle(
                    0, 0, G - 1, G - 1,
                    color=(0, 0, 0), batch=self.batch_arena
                )
                rect.visible = False
                row_rects.append(rect)
                
                border = shapes.Line(
                    0, 0, 0, 0,
                    color=(0, 0, 0, 40), batch=self.batch_arena
                )
                border.visible = False
                row_borders.append(border)
            
            self.arena_rectangles.append(row_rects)
            self.arena_borders.append(row_borders)
        
        # === 当前方块和幽灵方块 ===
        self.active_piece_rects = [
            shapes.Rectangle(0, 0, G - 1, G - 1, batch=self.batch_active_piece)
            for _ in range(16)
        ]
        
        self.ghost_piece_rects = [
            shapes.Rectangle(0, 0, G - 1, G - 1, batch=self.batch_active_piece)
            for _ in range(16)
        ]
        
        self.ghost_piece_outlines = [
            shapes.Box(0, 0, G - 1, G - 1, color=(255, 255, 255, 140), batch=self.batch_active_piece)
            for _ in range(16)
        ]
        
        for rect in self.active_piece_rects + self.ghost_piece_rects + self.ghost_piece_outlines:
            rect.visible = False
        
        # === 侧边栏 ===
        self._create_sidebar_ui(G, P, R, game_area_width)
        
        # === 粒子池 ===
        self.particle_rectangles = [
            shapes.Rectangle(0, 0, 1, 1, batch=self.batch_particles)
            for _ in range(MAX_PARTICLES)
        ]
        for rect in self.particle_rectangles:
            rect.visible = False
        
        # === 叠加层 ===
        self.overlay_group_bg = pyglet.graphics.Group(order=100)
        self.overlay_group_fg = pyglet.graphics.Group(order=101)
        
        # 容器背景 (多层复合)
        self.overlay_box_bg = shapes.RoundedRectangle(
            0, 0, 0, 0, radius=int(12 * R), color=(10, 15, 30, 240),
            batch=self.batch_overlay, group=self.overlay_group_bg
        )
        # 容器边框 (呼吸微光)
        self.overlay_box_border = shapes.Box(
            0, 0, 0, 0, color=(56, 189, 248, 180),
            thickness=1, batch=self.batch_overlay, group=self.overlay_group_bg
        )
        # 装饰物：4个角的 L 型饰件
        self.overlay_accents = []
        for _ in range(8): # 4个角，每个角两根线
            line = shapes.Line(0, 0, 0, 0, thickness=2, color=(56, 189, 248, 255),
                             batch=self.batch_overlay, group=self.overlay_group_fg)
            self.overlay_accents.append(line)
        
        self.overlay_title = text.Label(
            "", font_name=self.font_name, font_size=self.font_size_large, weight='bold',
            anchor_x='center', anchor_y='center', color=(255, 255, 255, 255),
            batch=self.batch_overlay, group=self.overlay_group_fg
        )
        self.overlay_mode = text.Label(
            "", font_name=self.font_name, font_size=int(14 * R),
            anchor_x='center', anchor_y='center', color=(255, 255, 255, 255),
            batch=self.batch_overlay, group=self.overlay_group_fg
        )
        self.overlay_hint = text.Label(
            "", font_name=self.font_name, font_size=int(11 * R),
            anchor_x='center', anchor_y='center', color=(148, 163, 184, 255),
            multiline=True, width=int(260 * R), align='center',
            batch=self.batch_overlay, group=self.overlay_group_fg
        )
    
    def _create_sidebar_ui(self, grid_size, padding, ratio, game_area_width):
        G, P, R = grid_size, padding, ratio
        self.sidebar_x = P + game_area_width + int(24 * R)
        self.box_width = int(180 * R)
        self.box_height_preview = int(145 * R)
        self.box_height_stat = int(82 * R)
        self.separator = int(16 * R)
        self.label_padding_x = int(18 * R)
        self.label_padding_y = int(22 * R)
        self.R, self.P = R, P

        # 创建预览方块池
        self.hold_piece_rects = [shapes.Rectangle(0,0,G-1,G-1, batch=self.batch_ui, group=self.ui_group_foreground) for _ in range(16)]
        self.next_piece_rects = [shapes.Rectangle(0,0,G-1,G-1, batch=self.batch_ui, group=self.ui_group_foreground) for _ in range(16)]
        for r in self.hold_piece_rects + self.next_piece_rects: r.visible = False

        # 创建侧边栏容器
        self.sidebar_boxes = []
        for i in range(5):
            h = self.box_height_preview if i < 2 else (int(self.box_height_stat * 1.5) if i == 4 else self.box_height_stat)
            box = shapes.RoundedRectangle(self.sidebar_x, 0, self.box_width, h, radius=int(10 * R),
                                        color=(*CARD_BG, 180), batch=self.batch_ui, group=self.ui_group_background)
            self.sidebar_boxes.append(box)

        # 创建所有标签
        self.labels = {
            'next': text.Label("下一个", font_name=self.font_name, font_size=self.font_size_small, color=(*TEXT_GREY, 255), batch=self.batch_ui, group=self.ui_group_foreground),
            'hold': text.Label("暂存", font_name=self.font_name, font_size=self.font_size_small, color=(*TEXT_GREY, 255), batch=self.batch_ui, group=self.ui_group_foreground),
            'score_title': text.Label("得分", font_name=self.font_name, font_size=self.font_size_small, color=(*TEXT_GREY, 255), batch=self.batch_ui, group=self.ui_group_foreground),
            'score_value': text.Label("0", font_name=self.font_name, font_size=self.font_size_main, weight='bold', color=(*PRIMARY_COLOR, 255), anchor_y='top', batch=self.batch_ui, group=self.ui_group_foreground),
            'level_title': text.Label("等级", font_name=self.font_name, font_size=self.font_size_small, color=(*TEXT_GREY, 255), batch=self.batch_ui, group=self.ui_group_foreground),
            'level_value': text.Label("1", font_name=self.font_name, font_size=self.font_size_main, weight='bold', color=(*PRIMARY_COLOR, 255), anchor_y='top', batch=self.batch_ui, group=self.ui_group_foreground),
            'stat_title': text.Label("技术统计", font_name=self.font_name, font_size=self.font_size_small, color=(*TEXT_GREY, 255), batch=self.batch_ui, group=self.ui_group_foreground),
            'stat_1': text.Label("单行: 0", font_name=self.font_name, font_size=int(10 * R), color=(255, 255, 255, 200), batch=self.batch_ui, group=self.ui_group_foreground),
            'stat_2': text.Label("双行: 0", font_name=self.font_name, font_size=int(10 * R), color=(255, 255, 255, 200), batch=self.batch_ui, group=self.ui_group_foreground),
            'stat_3': text.Label("三行: 0", font_name=self.font_name, font_size=int(10 * R), color=(255, 255, 255, 200), batch=self.batch_ui, group=self.ui_group_foreground),
            'stat_4': text.Label("四行: 0", font_name=self.font_name, font_size=int(10 * R), weight='bold', color=(251, 146, 60, 255), batch=self.batch_ui, group=self.ui_group_foreground),
        }
        for l in self.labels.values(): l.x = self.sidebar_x + self.label_padding_x

        # 操作提示标签
        self.hints = [("方向键","移动 & 旋转"),("空格","硬降落"),("C/Shift","暂存"),("P / R","暂停 / 重置")]
        self.hint_labels = []
        for _ in range(len(self.hints)):
            kl = text.Label("", font_name=self.font_name, font_size=self.font_size_hint, weight='bold', color=(255,255,255,255), batch=self.batch_ui, group=self.ui_group_foreground)
            al = text.Label("", font_name=self.font_name, font_size=self.font_size_hint, color=(*TEXT_GREY,255), batch=self.batch_ui, group=self.ui_group_foreground)
            self.hint_labels.extend([kl, al])
        
        self._update_sidebar_layout()
        
    def _update_sidebar_layout(self):
        P, R, sep, hb, hs = self.P, self.R, self.separator, self.box_height_preview, self.box_height_stat
        self.offset_next = P
        self.offset_hold = self.offset_next + hb + sep if self.hold_enabled else -1000
        self.offset_score = (self.offset_hold if self.hold_enabled else self.offset_next) + hb + sep
        self.offset_level, self.offset_stats = self.offset_score + hs + sep, self.offset_score + hs*2 + sep*2
        y_list = [self.offset_next, self.offset_hold, self.offset_score, self.offset_level, self.offset_stats]
        h_list = [hb, hb, hs, hs, int(hs*1.5)]
        for i, box in enumerate(self.sidebar_boxes):
            box.y = self.flip_y(y_list[i] + h_list[i]); box.visible = (i!=1 or self.hold_enabled)
        lx, ly = self.label_padding_x, self.label_padding_y
        for k, y in zip(['next','hold','score_title','level_title'], y_list[:4]):
            self.labels[k].y = self.flip_y(y + ly); self.labels[k].visible = (k!='hold' or self.hold_enabled)
        self.labels['score_value'].y = self.flip_y(self.offset_score + ly + int(26*R))
        self.labels['level_value'].y = self.flip_y(self.offset_level + ly + int(26*R))
        sy, lh = self.offset_stats + ly, int(18*R)
        self.labels['stat_title'].y = self.flip_y(sy)
        for i in range(1,5): self.labels[f'stat_{i}'].y = self.flip_y(sy + lh*i + int(4*R))
        hx, hy, lh = self.sidebar_x+int(5*R), self.offset_stats+int(hs*1.5)+int(28*R), int(19*R)
        for i, (k, a) in enumerate(self.hints):
            self.hint_labels[i*2].x, self.hint_labels[i*2].y, self.hint_labels[i*2].text = hx, self.flip_y(hy+i*lh), k
            self.hint_labels[i*2+1].x, self.hint_labels[i*2+1].y, self.hint_labels[i*2+1].text = self.sidebar_x+int(54*R), self.flip_y(hy+i*lh), a
    
    def flip_y(self, game_y):
        return self.physical_height - game_y
    
    # ===== AI 演示模式核心算法 =====
    
    def _analyze_holes(self, arena, rows, cols):
        """扫描并返回空洞数量及上方遮盖的块数"""
        holes, blocks_above_holes = 0, 0
        for x in range(cols):
            blocks = 0
            for y in range(rows):
                if arena[y][x]: 
                    blocks += 1
                elif blocks: 
                    holes += 1
                    blocks_above_holes += blocks
        return holes, blocks_above_holes

    def _analyze_wells(self, col_heights, rows, main_well_col):
        """扫描所有列的井位深度"""
        wells = []
        cols = len(col_heights)
        for x in range(cols):
            l = col_heights[x-1] if x > 0 else rows
            r = col_heights[x+1] if x < cols - 1 else rows
            if (depth := min(l, r) - col_heights[x]) > 0:
                wells.append((depth, x))
        return wells

    def ai_evaluate_board(self, test_arena, lines_cleared, is_high_risk, landing_y=None, piece_x=0, piece_type=None, piece_mat=None, i_distance=99):
        """
        AI 核心评估算法：模块化重构版 + 7-Bag 记牌
        i_distance: I 块最多还要几手才到（越小越近，0=下一个就是）
        """
        cols, rows = len(test_arena[0]), len(test_arena)
        main_well_col = cols - 1
        
        # 1. 基础状态分析 (提取 col_heights)
        col_heights = [next((rows - y for y in range(rows) if test_arena[y][x]), 0) for x in range(cols)]
        max_h = max(col_heights)
        
        # 2. 调用模块化工具扫描空洞和井位
        holes, blocks_above_holes = self._analyze_holes(test_arena, rows, cols)
        wells = self._analyze_wells(col_heights, rows, main_well_col)
        
        # 3. 转换率 (Transitions) 计算
        row_transitions = sum((test_arena[y][x] > 0) != (test_arena[y][x+1] > 0) for y in range(rows) for x in range(cols-1))
        row_transitions += sum(1 for y in range(rows) if test_arena[y][0] == 0)  # 仅惩罚左边界空洞，井位(右边界)按设计应为空
        col_transitions = sum((test_arena[y][x] > 0) != (test_arena[y+1][x] > 0) for x in range(cols) for y in range(rows-1))
        col_transitions += sum(1 for x in range(cols) if test_arena[rows-1][x] == 0)

        # 4. 战术分析：13+1 策略监控
        # 修正：left_heights 仅包含地基 (0-11列)，排除第 12 索引列 (即第 13 列墙体)
        left_heights = col_heights[:main_well_col - 1]
        left_max = max(left_heights) if left_heights else 0
        left_min = min(left_heights) if left_heights else 0
        left_avg = sum(left_heights) / float(len(left_heights)) if left_heights else 0
        h14, h13 = col_heights[main_well_col], col_heights[main_well_col - 1]
        
        well_reward, well_penalty = 0, 0
        if is_high_risk:
            # 高危保命：适度惩罚散井，防止恐慌
            well_penalty += sum((d**2) * 150000.0 for d, x in wells if x != main_well_col)
            if h13 > h14 and h14 < 5: 
                well_reward = (min(h13-h14, left_max+1) ** 2) * 15000.0 + 50000.0
        else:
            # 平时战术：严禁堵井，积极蓄力
            well_penalty += sum((d**2) * 100000.0 for d, x in wells if x != main_well_col)
            if h13 > h14:
                base_well = (min(h13-h14, left_max+1) ** 2) * 20000.0 + 100000.0
                # 7-Bag 记牌修正：I 块近则加大保井决心，I 块远则保持原样
                if i_distance <= 3:
                    base_well *= 1.5  # I 块近在眼前，死保竖井
                well_reward = base_well
            elif h14 > h13:
                well_penalty += (h14 - h13) * AI_WELL_ABUSE_PENALTY
        
        # 4.5 重点防护：防止 13 列过高 (Skyscraper Penalty)
        # 修正：以地基“平均高度”为准进行限高，强迫 AI 必须推平地基才能涨墙
        tower_diff = h13 - left_avg
        if tower_diff > 3:
            well_penalty += (tower_diff - 3) * AI_SKYSCRAPER_PENALTY
            
        # 4.6 注入“天平约束”：防止左右失衡导致的侧重现象
        mid = (main_well_col - 1) // 2
        l_side_avg = sum(left_heights[:mid]) / float(mid) if mid > 0 else 0
        r_side_avg = sum(left_heights[mid:]) / float(len(left_heights)-mid) if mid < len(left_heights) else 0
        balance_penalty = abs(l_side_avg - r_side_avg) * 150000.0 if abs(l_side_avg - r_side_avg) > 2 else 0

        # 5. 精确检测：本次移动是否污染了 14 列井位 (像素级)
        occupies_well = False
        if piece_mat:
            for y_offset, row in enumerate(piece_mat):
                for x_offset, val in enumerate(row):
                    if val and (piece_x + x_offset) == main_well_col:
                        occupies_well = True; break
                if occupies_well: break

        # 6. 确定消行奖金阶梯 (使用 .get 增加安全性)
        if is_high_risk:
            # 高压保命：允许 3 行作为紧急泄压手段，但 4 行仍是最终目标
            line_bonus = {0:0, 1:100000.0, 2:250000.0, 3:40000000.0, 4:80000000.0}.get(lines_cleared, 0)
        else:
            # 铁律：非保命模式下严禁 3 行消除（视为严重战术失误），强制 AI 锁定 Tetris 状态
            line_bonus = {0:0, 1:-50000.0, 2:-100000.0, 3:-50000000.0, 4:AI_TETRIS_REWARD}.get(lines_cleared, 0)
            # 7-Bag 记牌修正：I 块近且井就绪 -> 加重消 1-2 行的惩罚（别浪费 Tetris 机会）
            if i_distance <= 3 and h13 > h14 and h14 == 0:
                if lines_cleared in (1, 2):
                    line_bonus *= 2.0  # 双倍惩罚：I 块马上到，别消小行破坏局面

        # 6.5 提取基础指标 (供后续评分使用)
        landing_penalty = (rows - landing_y) * AI_LANDING_PENALTY if landing_y is not None else 0
        left_bumpiness = sum((col_heights[x] - col_heights[x+1])**2 for x in range(main_well_col - 2))
        row_integrity = sum((sum(1 for x in range(main_well_col) if test_arena[y][x]>0)**2) * AI_ROW_INTEGRITY_FACTOR for y in range(rows))
        center_pref = 0
        if piece_x is not None:
             # 鼓励方块放在左侧堆叠区中心（0-12列的中心=6），而非全场中心
             p_width = len(piece_mat[0]) if piece_mat else 2
             stack_center = (main_well_col - 1) / 2.0  # 左侧堆叠区中心
             dist_from_center = abs(piece_x + (p_width / 2.0) - stack_center)
             center_pref = max(0, 1.0 - (dist_from_center / stack_center)) * 15000.0
        base_variance = (left_max - left_min) * 50000.0

        # 7. 评分系统大融合
        if is_high_risk:
            # === 绝地求生模式：生存率高于一切 ===
            # 1. 放弃所有“美学”约束，只求降高和消行
            score = (
                line_bonus 
                - (sum(col_heights) * AI_HEIGHT_PENALTY * 200.0) # 极高权重的拉低
                - (max_h * AI_MAX_HEIGHT_PENALTY * 200.0)
                - (holes * AI_HOLE_PENALTY * 0.1)           # 容忍一定的空洞以换取消行
                - (left_bumpiness * AI_BUMPINESS_PENALTY * 0.2)
                - (landing_penalty * 10.0)
                + row_integrity * 0.1 
            )
        else:
            # === 正常模式：追求蓄力和 13+1 策略 ===
            # 加入 cankao.py 的低点差异惩罚 (Valley Penalty)
            valley_penalty = 0
            if left_heights:
                valley_penalty = sum(((left_max - h)**2) * 40000.0 for h in left_heights if h < left_max)
            
            # 加入井位溢出保护
            overflow_penalty = 0
            if h14 > (left_min + 2):
                overflow_penalty = (h14 - left_min) * AI_WELL_ABUSE_PENALTY

            score = (
                line_bonus + well_reward + row_integrity + center_pref
                - (sum(col_heights) * AI_HEIGHT_PENALTY * 15.0)
                - (row_transitions * AI_ROW_TRANSITION_PENALTY)
                - (col_transitions * AI_COL_TRANSITION_PENALTY) 
                - (left_bumpiness * AI_BUMPINESS_PENALTY * 5.0)
                - (holes * AI_HOLE_PENALTY * 20.0)
                - (blocks_above_holes * AI_BLOCK_COVER_PENALTY)
                - well_penalty - base_variance - balance_penalty - valley_penalty - overflow_penalty
                - (max_h * AI_MAX_HEIGHT_PENALTY * 20.0)
                - (landing_penalty * 3.0)
            )

        # 8. 注入铁律罚金：全时段战略储备
        if not is_high_risk and occupies_well and lines_cleared < 4:
            if lines_cleared == 0:
                # 纯堵井（没消行）-> 毁灭级惩罚
                score -= AI_MELTDOWN_PENALTY
            else:
                # 消了 1-3 行但占了井位 -> 浪费/滥用惩罚
                score -= AI_I_PIECE_WASTE_PENALTY if piece_type == 'I' else AI_WELL_ABUSE_PENALTY

        return score

    def ai_find_best_move(self):
        """二级搜索：评估当前与暂存方块的所有落点"""
        col_h = [next((GAME_ROWS - y for y in range(GAME_ROWS) if self.arena[y][x]), 0) for x in range(GAME_COLS)]
        avg_h = sum(col_h) / float(GAME_COLS)
        
        # 调节后的保命开关：平均高度 > 10 (约 1/3 高度) 进入，低于 3 行退出
        # 注意：在 30 行高度的设置下，10 行 average 已经非常危险了
        if not self.ai_conservative_mode:
            if avg_h > 11.0:
                self.ai_conservative_mode = True
        else:
            if avg_h < 4.0:
                self.ai_conservative_mode = False
                
        current_mode = self.ai_conservative_mode
        
        candidates = [{'mat': self.current_piece_matrix, 'hold': False, 'type': self.current_piece_type}]
        if self.hold_enabled and self.can_hold:
            h_type = self.hold_piece_type or self.next_piece_type
            candidates.append({'mat': [row[:] for row in SHAPES[h_type]], 'hold': True, 'type': h_type})

        # ★ 7-Bag 记牌器：计算 I 块最多还要几手才到 ★
        if self.next_piece_type == 'I':
            i_distance = 1  # 下一个就是 I
        elif 'I' in self.bag:
            i_distance = len(self.bag)  # I 在当前袋子里，最迟 bag 耗尽时出现
        else:
            i_distance = len(self.bag) + 7  # I 在下一个袋子里

        scored_moves1 = []
        for cand in candidates:
            m_base = [row[:] for row in cand['mat']]
            p_type = cand['type']
            for rot1 in range(4):
                m1 = [row[:] for row in m_base]
                for _ in range(rot1):
                    m1 = [list(row) for row in zip(*m1[::-1])]
                
                for x1 in range(-2, GAME_COLS + 2):
                    if not self._check_collision_static(self.arena, {'x': x1, 'y': 0}, m1):
                        y1 = 0
                        while not self._check_collision_static(self.arena, {'x': x1, 'y': y1+1}, m1):
                            y1 += 1
                        
                        arena1, clear1 = self._simulate_placement(self.arena, x1, y1, m1)
                        s1 = self.ai_evaluate_board(arena1, clear1, current_mode, landing_y=y1, piece_x=x1, piece_type=p_type, piece_mat=m1, i_distance=i_distance)
                        scored_moves1.append((s1, rot1, x1, y1, m1, arena1, cand['hold'], p_type))
        
        scored_moves1.sort(key=lambda x: x[0], reverse=True)
        
        # --- 第二层搜索 (增强采样) ---
        best_overall_score = float('-inf')
        final_rot, final_x, final_y, final_mat = 0, 0, 0, None
        final_hold = False
        
        search_limit = AI_SEARCH_LIMIT
        for s1, rot1, x1, y1, mat1, arena1, is_hold, p1_type in scored_moves1[:search_limit]:
            best_s2, m2_base = float('-inf'), [row[:] for row in self.next_piece_matrix]
            p2_type = self.next_piece_type

            for rot2 in range(4):
                m2 = [row[:] for row in m2_base]
                for _ in range(rot2):
                    m2 = [list(row) for row in zip(*m2[::-1])]
                
                for x2 in range(-2, GAME_COLS + 2):
                    if not self._check_collision_static(arena1, {'x': x2, 'y': 0}, m2):
                        y2 = 0
                        while not self._check_collision_static(arena1, {'x': x2, 'y': y2+1}, m2):
                            y2 += 1
                        arena2, clear2 = self._simulate_placement(arena1, x2, y2, m2)
                        s2 = self.ai_evaluate_board(arena2, clear2, current_mode, landing_y=y2, piece_x=x2, piece_type=p2_type, piece_mat=m2, i_distance=max(0, i_distance - 1))
                        if s2 > best_s2:
                            best_s2 = s2
            
            # 综合评分：当前步评分 + 期望的下一步最佳评分 (1.0 权重，深度前瞻)
            total_s = s1 + (best_s2 if best_s2 != float('-inf') else 0)
            if total_s > best_overall_score:
                best_overall_score = total_s
                final_rot, final_x, final_y, final_mat = rot1, x1, y1, mat1
                final_hold = is_hold
        
        if not final_mat and scored_moves1:
            # 安全降级：如果没有找到两层搜索的最佳解，取第一层搜索的最佳解
            s1, final_rot, final_x, final_y, final_mat, _, final_hold, _ = scored_moves1[0]
            best_overall_score = s1

        return final_rot, final_x, best_overall_score, final_y, final_mat, final_hold

    def _simulate_placement(self, arena, piece_x, piece_y, matrix):
        """模拟放置并返回结果，极致精简副本创建逻辑"""
        new_arena = [row[:] for row in arena]
        for y, row in enumerate(matrix):
            for x, val in enumerate(row):
                if val:
                    ay, ax = piece_y + y, piece_x + x
                    if 0 <= ay < GAME_ROWS and 0 <= ax < GAME_COLS:
                        new_arena[ay][ax] = val
        
        # 快速消行 (仅针对受影响行或全扫)
        new_arena = [r for r in new_arena if not all(r)]
        cleared = GAME_ROWS - len(new_arena)
        while len(new_arena) < GAME_ROWS:
            new_arena.insert(0, [0] * GAME_COLS)
        return new_arena, cleared

    def _check_collision_static(self, arena, pos, matrix):
        for y, row in enumerate(matrix):
            for x, value in enumerate(row):
                if value:
                    ay, ax = y + pos['y'], x + pos['x']
                    if (ay >= GAME_ROWS or ax < 0 or ax >= GAME_COLS or
                        (ay >= 0 and arena[ay][ax])):
                        return True
        return False
    
    def ai_execute_move(self, target_rotation, target_x, target_mat, should_hold=False):
        """
        将 AI 分解出的目标位置转换为一系列具体操作动作。
        如果包含 Hold，由于物理坐标会重置，需精准修正位移参考点。
        """
        if self.demo_ai_action is None:
            actions = []
            if should_hold:
                actions.append('hold')
                # hold 之后方块会重置到顶部中心，需计算当前 target_mat 的生成 X 坐标
                current_x = GAME_COLS // 2 - len(target_mat[0]) // 2
            else:
                current_x = self.piece_position['x']
                
            for _ in range(target_rotation):
                actions.append('rotate')
                
            dx = target_x - current_x
            for _ in range(abs(dx)):
                actions.append('right' if dx > 0 else 'left')
            actions.append('drop')
            self.demo_ai_action, self.demo_ai_step = actions, 0
        
        # 执行一个动作
        if self.demo_ai_step < len(self.demo_ai_action):
            action = self.demo_ai_action[self.demo_ai_step]
            
            if action == 'hold':
                self.hold_piece()
            elif action == 'rotate':
                self.rotate_piece(1)
            elif action == 'left':
                self.move_piece_horizontal(-1)
            elif action == 'right':
                self.move_piece_horizontal(1)
            if action == 'drop':
                self.hard_drop()
                self.demo_ai_action, self.demo_ai_step = None, 0
                return True
            
            self.demo_ai_step += 1
            if self.demo_ai_action and self.demo_ai_step < len(self.demo_ai_action):
                if self.demo_ai_action[self.demo_ai_step] == 'drop':
                    self.hard_drop()
                    self.demo_ai_action, self.demo_ai_step = None, 0
                    return True
        
        return False  # 还在执行中
    
    def enter_demo_mode(self):
        self.demo_mode, self.demo_ai_delay, self.demo_ai_action, self.demo_ai_step, self.demo_ai_target_info = True, 0.0, None, 0, None
        self.reset_game(self.selected_level)
    
    def exit_demo_mode(self):
        self.demo_mode, self.idle_timer, self.is_game_over = False, 0.0, True
    
    def reset_game(self, start_level=1):
        self.arena = [[0] * GAME_COLS for _ in range(GAME_ROWS)]
        self.start_level = start_level
        self.score, self.level, self.lines_cleared = 0, start_level, 0
        self.line_stats = {1:0, 2:0, 3:0, 4:0}
        
        self.bag = self._fill_bag()
        self.next_piece_type = self._get_next_from_bag()
        self.next_piece_matrix = self._get_initial_matrix(self.next_piece_type)
        self.lock_delay_timer, self.lock_delay_limit, self.max_lock_resets, self.lock_delay_moves = 0.0, 0.5, 15, 0
        self.drop_counter, self.hold_piece_type, self.can_hold = 0, None, True
        self.particles, self.is_paused, self.is_game_over, self.is_on_ground, self.lock_timer = [], False, False, False, 0
        self.spawn_piece()
    
    def _get_initial_matrix(self, piece_type):
        """获取方块的初始矩阵，维持 orientation 一致性以便 AI 准确计算旋转"""
        return [row[:] for row in SHAPES[piece_type]]

    def _fill_bag(self):
        types = list(SHAPES.keys())
        random.shuffle(types); return types

    def _get_next_from_bag(self):
        if not self.bag: self.bag = self._fill_bag()
        return self.bag.pop()

    def spawn_piece(self):
        self.current_piece_type, self.current_piece_matrix = self.next_piece_type, self.next_piece_matrix
        if self.demo_mode: self.demo_ai_target_info = None
        self.next_piece_type = self._get_next_from_bag()
        self.next_piece_matrix = self._get_initial_matrix(self.next_piece_type)
        self.piece_position = {'x': GAME_COLS//2 - len(self.current_piece_matrix[0])//2, 'y': 0}
        
        # 重置锁定延迟相关状态
        self.lock_delay_timer = 0
        self.lock_delay_moves = 0  # 限制重置次数
        
        self.can_hold = True
        self.last_move_was_rotate = False  # 追踪最后一次动作是否为旋转
        self.t_spin_detected = False      # 记录当前是否处于 T-Spin 状态
        
        if self.check_collision(self.piece_position, self.current_piece_matrix):
            self.is_game_over = True
            self.play_sound('gameover')
    
    def check_collision(self, position, matrix):
        for y, row in enumerate(matrix):
            for x, val in enumerate(row):
                if val:
                    ay, ax = y + position['y'], x + position['x']
                    if ay >= GAME_ROWS or ax < 0 or ax >= GAME_COLS or (ay >= 0 and self.arena[ay][ax]): return True
        return False
    
    def rotate_piece(self, direction):
        """旋转方块 - 加入简单的踢墙补偿 (SRS 简化版)"""
        if self.is_game_over or self.is_paused:
            return
            
        old_matrix = self.current_piece_matrix
        old_x = self.piece_position['x']
        old_y = self.piece_position['y']
        
        # 旋转矩阵
        new_matrix = [
            [old_matrix[y][x] for y in range(len(old_matrix))]
            for x in range(len(old_matrix[0]))
        ]
        
        if direction > 0:
            for row in new_matrix:
                row.reverse()
        else:
            new_matrix.reverse()
        
        # 尝试踢墙偏移（左、右、上）
        offsets = [(0, 0), (-1, 0), (1, 0), (0, -1), (-2, 0), (2, 0)]
        for dx, dy in offsets:
            test_pos = {'x': old_x + dx, 'y': old_y + dy}
            if not self.check_collision(test_pos, new_matrix):
                self.piece_position['x'] = test_pos['x']
                self.piece_position['y'] = test_pos['y']
                self.current_piece_matrix = new_matrix
                self._reset_lock_timer()
                self.last_move_was_rotate = True # 标记最后动作是旋转
                self.play_sound('rotate')
                
                # 如果是 T 块，预检测 T-Spin 状态
                if self.current_piece_type == 'T':
                    self.t_spin_detected = self._check_t_spin()
                return
        
        # 失败则不执行任何操作
    
    def move_piece_down(self):
        """方块下移"""
        self.piece_position['y'] += 1
        
        if self.check_collision(self.piece_position, self.current_piece_matrix):
            self.piece_position['y'] -= 1
            self.is_on_ground = True
        else:
            self.last_move_was_rotate = False # 移动会清除旋转标记
            self.is_on_ground = False
        
        self.drop_counter = 0

    def _check_t_spin(self):
        """T-Spin 检测：中心 3x3 区域的四个角有 3 个被占据"""
        pos = self.piece_position
        # T 块中心的 4 个对角坐标（相对坐标）
        corners = [(0, 0), (2, 0), (0, 2), (2, 2)]
        occupied = 0
        for cx, cy in corners:
            ax, ay = pos['x'] + cx, pos['y'] + cy
            # 墙壁也算占据
            if ax < 0 or ax >= GAME_COLS or ay >= GAME_ROWS:
                occupied += 1
            elif ay >= 0 and self.arena[ay][ax]:
                occupied += 1
        return occupied >= 3

    def move_piece_horizontal(self, dx):
        """方块水平移动"""
        self.piece_position['x'] += dx
        
        if self.check_collision(self.piece_position, self.current_piece_matrix):
            self.piece_position['x'] -= dx
            return False
        
        self.last_move_was_rotate = False # 移动会清除旋转标记
        self.is_on_ground = self.check_collision(
            {'x': self.piece_position['x'], 'y': self.piece_position['y'] + 1},
            self.current_piece_matrix
        )
        self._reset_lock_timer()
        self.play_sound('move')
        return True
    
    def hard_drop(self):
        """硬降落"""
        while not self.check_collision(self.piece_position, self.current_piece_matrix):
            self.piece_position['y'] += 1
        
        self.piece_position['y'] -= 1
        self.play_sound('drop')
        self.lock_piece()
    
    def lock_piece(self):
        """锁定方块"""
        # 将方块合并到游戏区
        for y, row in enumerate(self.current_piece_matrix):
            for x, value in enumerate(row):
                if value:
                    arena_y = y + self.piece_position['y']
                    arena_x = x + self.piece_position['x']
                    if 0 <= arena_y < GAME_ROWS and 0 <= arena_x < GAME_COLS:
                        self.arena[arena_y][arena_x] = value
        
        self.clear_lines()
        self.spawn_piece()
        
        self.is_on_ground = False
        self.lock_timer = 0
        self.play_sound('lock')
    
    def hold_piece(self):
        """暂存方块"""
        if not self.hold_enabled or not self.can_hold or self.is_paused or self.is_game_over:
            return
        
        if self.hold_piece_type is None:
            self.hold_piece_type = self.current_piece_type
            self.spawn_piece()
        else:
            # 交换当前方块和暂存方块
            self.current_piece_type, self.hold_piece_type = \
                self.hold_piece_type, self.current_piece_type
            self.current_piece_matrix = [row[:] for row in SHAPES[self.current_piece_type]]
            self.piece_position = {
                'x': GAME_COLS // 2 - len(self.current_piece_matrix[0]) // 2,
                'y': 0
            }
        
        self.can_hold = False
        self.play_sound('rotate')
    
    def clear_lines(self):
        lines_count, y = 0, GAME_ROWS-1
        while y >= 0:
            if 0 not in self.arena[y]:
                self.create_line_clear_particles(y, self.arena[y][:])
                self.arena.pop(y); self.arena.insert(0, [0]*GAME_COLS); lines_count += 1
            else: y -= 1
        if lines_count == 0:
            if self.t_spin_detected: self.score += 100
            return
        if lines_count in self.line_stats: self.line_stats[lines_count] += 1
        scores = {1:100, 2:300, 3:500, 4:800}
        ts_scores = {1:800, 2:1200, 3:1600}
        self.score += (ts_scores.get(lines_count, 400) if self.t_spin_detected else scores.get(lines_count, 0)) * self.level
        self.lines_cleared += lines_count; self.play_sound('clear')
        new_level = self.start_level + (self.lines_cleared // 10)
        if new_level > self.level:
            self.level = new_level
            self.play_sound('levelup')
    
    def create_line_clear_particles(self, row_y, row_data):
        if len(self.particles) >= MAX_PARTICLES or row_y < 0 or row_y >= GAME_ROWS: return
        G, P = self.grid_size, self.padding
        pts = []
        for x, value in enumerate(row_data):
            if value and len(self.particles) + len(pts) < MAX_PARTICLES:
                px, py = P + x*G + G//2, self.flip_y(P + row_y*G + G//2)
                for _ in range(min(6, MAX_PARTICLES - len(self.particles) - len(pts))):
                    pts.append(Particle(px, py, COLORS[value]))
        self.particles.extend(pts)
    
    def get_ghost_position(self):
        gp = self.piece_position.copy()
        while not self.check_collision(gp, self.current_piece_matrix): gp['y'] += 1
        gp['y'] -= 1; return gp
    
    def on_key_press(self, symbol, modifiers):
        """键盘按下事件"""
        # === 演示模式退出逻辑 ===
        if self.demo_mode:
            self.exit_demo_mode()
            return  # 退出演示模式，不处理其他输入
        
        # 重置静置计时器（玩家有操作）
        self.idle_timer = 0.0
        
        self.input_handler.keys_pressed.add(symbol)
        
        # 过滤 OS 的自动重复事件
        if symbol in self.input_handler.key_latches:
            return
        
        # 非方向键加锁
        if symbol not in (key.LEFT, key.RIGHT, key.DOWN):
            self.input_handler.key_latches.add(symbol)
        
        # 功能键处理
        if symbol == key.P and not self.is_game_over:
            self.is_paused = not self.is_paused
        
        if symbol == key.R:
            self.reset_game(self.selected_level)
            self.is_game_over = True
            return
        
        if self.is_game_over:
            if symbol in (key.TAB, key.S):
                self.selected_level = 100 if self.selected_level == 1 else 1
            if symbol == key.H: # H 键切换暂存
                self.hold_enabled = not self.hold_enabled
                self._update_sidebar_layout() # 更新实时布局
                self.play_sound('move')
            if symbol in (key.ENTER, key.SPACE, key._1, key._2):
                self.reset_game(self.selected_level)
            return
        
        if self.is_paused:
            return
        
        # 游戏操作
        if symbol == key.UP:
            self.rotate_piece(1)
        elif symbol == key.SPACE:
            self.hard_drop()
        elif symbol in (key.C, key.LSHIFT, key.RSHIFT):
            self.hold_piece()
    
    def on_key_release(self, symbol, modifiers):
        """键盘释放事件"""
        self.input_handler.keys_pressed.discard(symbol)
        
        # 延迟解锁（防止 OS 伪释放）
        def unlock_key(dt):
            self.input_handler.key_latches.discard(symbol)
        
        pyglet.clock.schedule_once(unlock_key, 0.05)
    
    def handle_gamepad_input(self, dt):
        """处理手柄输入及组合键重置"""
        # === 演示模式退出逻辑（手柄） ===
        if self.demo_mode and self.joysticks:
            # 检测任意手柄按键
            js = self.joysticks[0]
            try:
                if any(js.buttons) or abs(getattr(js, 'x', 0)) > 0.3 or abs(getattr(js, 'y', 0)) > 0.3:
                    self.exit_demo_mode()
                    return
            except Exception:
                pass
        
        # 手柄操作重置静置计时器
        if self.joysticks:
            js = self.joysticks[0]
            try:
                if any(js.buttons) or abs(getattr(js, 'x', 0)) > 0.3 or abs(getattr(js, 'y', 0)) > 0.3:
                    self.idle_timer = 0.0
            except Exception:
                pass
        
        # --- 软重置逻辑 (Select + Start 按住 1 秒) ---
        is_select_down = False
        is_start_down = False
        
        # 1. 检测键盘 (TAB + P)
        if key.TAB in self.input_handler.keys_pressed and key.P in self.input_handler.keys_pressed:
            is_select_down = True
            is_start_down = True
            
        # 2. 检测手柄
        if self.joysticks:
            js = self.joysticks[0]
            try:
                # Select 键: 7, 9
                if any(b < len(js.buttons) and js.buttons[b] for b in [7, 9]):
                    is_select_down = True
                # Start 键: 6, 8, 10
                if any(b < len(js.buttons) and js.buttons[b] for b in [6, 8, 10]):
                    is_start_down = True
            except Exception: pass
            
        if is_select_down and is_start_down:
            self.reset_hold_timer += dt
            if self.reset_hold_timer >= 1.0:
                self.reset_hold_timer = 0.0
                self.reset_game(self.selected_level)
                self.is_game_over = True  # 重置后进入停止（准备开始）状态
                self.play_sound('levelup') # 重置成功的声音反馈
                return
        else:
            self.reset_hold_timer = 0.0

        if not self.joysticks:
            return
        
        joystick = self.joysticks[0]
        
        # Start 键：暂停/开始
        if self.input_handler.check_gamepad_trigger(joystick, [6, 8, 10]):
            if self.is_game_over:
                self.reset_game(self.selected_level)
            else:
                self.is_paused = not self.is_paused
        
        if self.is_game_over:
            # Select 键：切换难度
            if self.input_handler.check_gamepad_trigger(joystick, [7, 9]):
                self.selected_level = 100 if self.selected_level == 1 else 1
            
            # X/Y 键：切换暂存 (按钮 2, 3)
            if self.input_handler.check_gamepad_trigger(joystick, [2, 3]):
                self.hold_enabled = not self.hold_enabled
                self._update_sidebar_layout() # 更新实时布局
                self.play_sound('move')
            
            # A 键：开始游戏
            if self.input_handler.check_gamepad_trigger(joystick, [0]):
                self.reset_game(self.selected_level)
            return
        
        if self.is_paused:
            return
        
        if self.input_handler.check_gamepad_trigger(joystick, [4, 5]): self.hold_piece()
        
        # A, B 键或十字键向上：旋转
        if self.input_handler.check_gamepad_trigger(joystick, [0, 1], axis_config=('hat_y', 0.5, True)):
            self.rotate_piece(1)
            
        # X, Y 键：硬降落
        if self.input_handler.check_gamepad_trigger(joystick, [2, 3]):
            self.hard_drop()
    
    def update_movement(self, dt):
        if self.is_paused or self.is_game_over: return
        
        key_l, key_r = key.LEFT in self.input_handler.keys_pressed, key.RIGHT in self.input_handler.keys_pressed
        gp_l, gp_r = False, False
        if self.joysticks:
            try:
                js = self.joysticks[0]
                gp_l = (getattr(js, 'x', 0) < -0.5 or getattr(js, 'hat_x', 0) < -0.5)
                gp_r = (getattr(js, 'x', 0) > 0.5 or getattr(js, 'hat_x', 0) > 0.5)
            except Exception as e:
                print(f"[!] Gamepad input read error: {e}")
        
        # 处理左右移动
        for direction, active, dx in [('left', key_l or gp_l, -1), ('right', key_r or gp_r, 1)]:
            if active:
                if not self.input_handler.move_active[direction]:
                    self.move_piece_horizontal(dx)
                    self.input_handler.move_timers[direction], self.input_handler.move_active[direction] = DAS_DELAY, True
                elif self.input_handler.move_timers[direction] <= 0:
                    self.move_piece_horizontal(dx)
                    self.input_handler.move_timers[direction] = ARR_DELAY
            else: self.input_handler.move_active[direction] = False
    
    def _reset_lock_timer(self):
        if self.lock_delay_moves < self.max_lock_resets:
            self.lock_delay_timer, self.lock_delay_moves = 0, self.lock_delay_moves + 1

    def update(self, dt):
        self.ui_time += dt
        self.handle_gamepad_input(dt)
        if self.demo_mode:
            if self.demo_target_score > 0 and self.score >= self.demo_target_score:
                self.exit_demo_mode()
                return
            if self.is_game_over:
                self.reset_game(self.selected_level)
                self.demo_ai_action = None
                return
            if not self.is_paused:
                self.demo_ai_delay += dt
                if self.demo_ai_delay >= 0.02:
                    self.demo_ai_delay = 0.0
                    if self.demo_ai_action is None:
                        br, bx, bs, by, bm, sh = self.ai_find_best_move()
                        self.ai_execute_move(br, bx, bm, sh)
                    else:
                        self.ai_execute_move(0, 0, None)
        else:
            if self.is_game_over:
                self.idle_timer += dt
                if self.idle_timer >= self.idle_threshold:
                    self.enter_demo_mode()
                    return
        
        self.update_movement(dt)
        self.input_handler.update_move_timers(dt)
        
        if not self.is_paused and not self.is_game_over:
            # 检测软降状态 (键盘向下键 或 手柄摇杆/十字键向下)
            is_soft_drop = (key.DOWN in self.input_handler.keys_pressed)
            if self.joysticks:
                try:
                    js = self.joysticks[0]
                    # 注意：手柄 Y 轴向下通常是正值，Hat Y 向下通常是负值
                    if getattr(js, 'y', 0) > 0.5 or getattr(js, 'hat_y', 0) < -0.5:
                        is_soft_drop = True
                except: pass

            if is_soft_drop:
                self.move_piece_down()
            
            is_ground = self.check_collision({'x':self.piece_position['x'], 'y':self.piece_position['y']+1}, self.current_piece_matrix)
            if is_ground:
                self.lock_delay_timer += dt
                if self.lock_delay_timer >= self.lock_delay_limit:
                    self.lock_piece()
            else:
                self.drop_counter += dt
                fall_speed = max(0.05, 1.0 * (0.9 ** (self.level - 1)))
                if self.drop_counter >= fall_speed:
                    self.drop_counter = 0
                    self.move_piece_down()
        try: self.particles = [p for p in self.particles if p.update(dt)]
        except Exception as e:
            print(f"[!] Particle reset warning: {e}")
            self.particles = []
    
    def on_draw(self):
        self.clear()
        self.labels['score_value'].text = str(self.score)
        self.labels['level_value'].text = str(self.level)
        
        # 视觉反馈：保命模式
        if self.demo_mode and hasattr(self, 'ai_conservative_mode'):
            if self.ai_conservative_mode:
                self.labels['stat_title'].text = "技术统计（保命模式）"
                self.labels['stat_title'].color = (255, 100, 100, 255)
            else:
                self.labels['stat_title'].text = "技术统计"
                self.labels['stat_title'].color = (148, 163, 184, 255) # TEXT_GREY

        if hasattr(self, 'line_stats'):
            for i in range(1, 5):
                self.labels[f'stat_{i}'].text = f"{['单','双','三','四'][i-1]}行: {self.line_stats[i]}"
        self.update_arena_ui()
        if not self.is_game_over and not self.is_paused:
            self.update_ghost_piece_ui()
            self.update_active_piece_ui()
        else:
            for r in (self.active_piece_rects + self.ghost_piece_rects + self.ghost_piece_outlines): r.visible = False
        self.update_preview_ui()
        self.update_particles_ui()
        if (self.is_paused or self.is_game_over) and not self.demo_mode:
            R = self.pixel_ratio
            if self.is_game_over:
                if self.score == 0:
                    self.overlay_title.text = "准  备  开  始"
                    self.overlay_title.color = (34, 197, 94, 255)
                else:
                    self.overlay_title.text = "游  戏  结  束"
                    self.overlay_title.color = (244, 63, 94, 255)
                is_h = self.selected_level > 1
                self.overlay_mode.text = f"模式: {'硬核 (Lv.100)' if is_h else '普通'}  |  暂存: [{'开' if self.hold_enabled else '关'}]"
                self.overlay_mode.color, self.overlay_hint.text = ((251,146,60,255) if is_h else (45,212,191,255)), "[Select] 难度 / [Start] 开始"
                self.overlay_mode.visible = True
            else:
                self.overlay_title.text = "游  戏  暂  停"
                self.overlay_title.color = (56, 189, 248, 255)
                self.overlay_mode.visible = False
                self.overlay_hint.text = "按下 P 键或功能键继续"
            cx, cy = (self.padding + (GAME_COLS*self.grid_size)//2), self.flip_y(self.padding + (GAME_ROWS*self.grid_size)//2)
            bw, bh = int(300*R), int(180*R)
            bx, by = cx-bw//2, cy-bh//2
            self.overlay_box_bg.x, self.overlay_box_bg.y, self.overlay_box_bg.width, self.overlay_box_bg.height = bx, by, bw, bh
            p = (math.sin(self.ui_time*3)+1)/2
            self.overlay_box_border.x, self.overlay_box_border.y, self.overlay_box_border.width, self.overlay_box_border.height = bx, by, bw, bh
            self.overlay_box_border.color = (56,189,248,int(100+p*100))
            al = int(15*R)
            acc_coords = [(bx,by+bh,bx+al,by+bh),(bx,by+bh,bx,by+bh-al),(bx+bw,by+bh,bx+bw-al,by+bh),(bx+bw,by+bh,bx+bw,by+bh-al),(bx,by,bx+al,by),(bx,by,bx,by+al),(bx+bw,by,bx+bw-al,by),(bx+bw,by,bx+bw,by+al)]
            for i, coords in enumerate(acc_coords):
                self.overlay_accents[i].x, self.overlay_accents[i].y, self.overlay_accents[i].x2, self.overlay_accents[i].y2, self.overlay_accents[i].visible = *coords, True
            self.overlay_title.position = (cx, cy + int(45 * R), 0)
            self.overlay_mode.position = (cx, cy + int(5 * R), 0)
            self.overlay_hint.position = (cx, cy - int(40 * R), 0)
            
            self.overlay_box_bg.visible = True
            self.overlay_box_border.visible = True
        else:
            self.overlay_box_bg.visible = self.overlay_box_border.visible = self.overlay_mode.visible = False
            self.overlay_title.text = self.overlay_hint.text = ""
            for acc in self.overlay_accents: acc.visible = False
        self.batch_background.draw()
        self.batch_grid.draw()
        self.batch_arena.draw()
        self.batch_active_piece.draw()
        self.batch_particles.draw()
        self.batch_ui.draw()
        
        if self.is_paused or self.is_game_over or self.demo_mode:
            self.batch_overlay.draw()
    
    def update_arena_ui(self):
        G, P = self.grid_size, self.padding
        for y in range(GAME_ROWS):
            for x in range(GAME_COLS):
                v, rect, border = self.arena[y][x], self.arena_rectangles[y][x], self.arena_borders[y][x]
                if v:
                    px, py = P + x*G, self.flip_y(P + y*G + G)
                    rect.x, rect.y, rect.color, rect.visible = px, py, COLORS[v], True
                    border.x, border.y, border.x2, border.y2, border.visible = px, py+G-1, px+G-1, py+G-1, True
                else: rect.visible = border.visible = False
    
    def update_active_piece_ui(self):
        G, P, index = self.grid_size, self.padding, 0
        for y, row in enumerate(self.current_piece_matrix):
            for x, v in enumerate(row):
                if v and index < len(self.active_piece_rects):
                    px, py = P + (x+self.piece_position['x'])*G, self.flip_y(P + (y+self.piece_position['y'])*G + G)
                    r = self.active_piece_rects[index]
                    r.x, r.y, r.color, r.visible = px, py, COLORS[v], True
                    index += 1
        for i in range(index, len(self.active_piece_rects)): self.active_piece_rects[i].visible = False
    
    def update_ghost_piece_ui(self):
        G, P, gp_pos, index = self.grid_size, self.padding, self.get_ghost_position(), 0
        for y, row in enumerate(self.current_piece_matrix):
            for x, v in enumerate(row):
                if v and index < len(self.ghost_piece_rects):
                    px, py = P + (x+gp_pos['x'])*G, self.flip_y(P + (y+gp_pos['y'])*G + G)
                    r, o = self.ghost_piece_rects[index], self.ghost_piece_outlines[index]
                    r.x, r.y, r.color, r.visible = px, py, (*CARD_BG, 100), True
                    o.x, o.y, o.color, o.visible = px, py, (*COLORS[v], 180), True
                    index += 1
        for i in range(index, len(self.ghost_piece_rects)): self.ghost_piece_rects[i].visible = self.ghost_piece_outlines[i].visible = False
    
    def update_preview_ui(self):
        """更新预览UI（暂存和下一个）"""
        # 更新暂存方块
        if self.hold_enabled:
            if self.hold_piece_type:
                self.update_preview_piece(
                    SHAPES[self.hold_piece_type],
                    self.hold_piece_rects,
                    self.offset_hold,
                    dimmed=not self.can_hold
                )
            else:
                for rect in self.hold_piece_rects:
                    rect.visible = False
        else:
            for rect in self.hold_piece_rects:
                rect.visible = False
        
        # 更新下一个方块
        self.update_preview_piece(
            self.next_piece_matrix,
            self.next_piece_rects,
            self.offset_next
        )
    
    def update_preview_piece(self, matrix, rect_pool, y_offset, dimmed=False):
        occ = [(x, y) for y, row in enumerate(matrix) for x, v in enumerate(row) if v]
        if not occ:
            for r in rect_pool: r.visible = False
            return
        mx, My, mX, MY = min(c[0] for c in occ), max(c[0] for c in occ), min(c[1] for c in occ), max(c[1] for c in occ)
        rw, rh, G = My-mx+1, MY-mX+1, self.grid_size
        ax, ay = (self.sidebar_x/G)+(self.box_width/G-rw)/2-mx, (y_offset/G)+(self.label_padding_y/G+0.3)+(self.box_height_preview/G-(self.label_padding_y/G+0.3)-rh)/2-mX
        idx = 0
        for y, row in enumerate(matrix):
            for x, val in enumerate(row):
                if val and idx < len(rect_pool):
                    rect_pool[idx].x, rect_pool[idx].y = int((x+ax)*G), self.flip_y(int((y+ay)*G)+G)
                    rect_pool[idx].color, rect_pool[idx].visible = ([int(c*0.4) for c in COLORS[val]]+[255] if dimmed else COLORS[val]), True
                    idx += 1
        for i in range(idx, len(rect_pool)): rect_pool[i].visible = False
    
    def update_particles_ui(self):
        index = 0
        for p in self.particles:
            if index < len(self.particle_rectangles):
                r = self.particle_rectangles[index]
                r.x, r.y, r.width, r.height = int(p.x)-p.size, int(p.y)-p.size, p.size*2, p.size*2
                r.color, r.visible = (*p.color, max(0, min(255, int(p.alpha)))), True
                index += 1
        for i in range(index, len(self.particle_rectangles)): self.particle_rectangles[i].visible = False
    
    def on_close(self):
        """窗口关闭清理"""
        for joystick in self.joysticks:
            try:
                joystick.close()
            except Exception as e:
                print(f"[!] Error closing joystick: {e}")
        
        super().on_close()

if __name__ == "__main__":
    game = TetrisGame()
    pyglet.app.run()