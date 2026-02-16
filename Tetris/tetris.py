"""
经典俄罗斯方块 - 专业重构版
- 支持 Retina HiDPI 原生渲染
- OrderedGroup 解决 UI 层级问题
- 全局粒子池管理防止内存泄漏
- 模块化输入处理系统
- 悦耳的合成音效
"""
import pyglet
from pyglet import shapes, text, clock
from pyglet.window import key
import random
import os
import time
import io
import struct
import math
import wave

# === 游戏常量 ===
GRID_SIZE = 24
GAME_ROWS = 30
GAME_COLS = 14
SIDEBAR_WIDTH = 200
PADDING = 20

# 全局粒子限制（防止内存泄漏）
MAX_PARTICLES = 1000

# 输入参数
DAS_DELAY = 0.180  # 延迟自动重复
ARR_DELAY = 0.040  # 自动重复速率
LOCK_DELAY = 0.500  # 落地锁定延迟

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
    'I': [[0,6,0,0],[0,6,0,0],[0,6,0,0],[0,6,0,0]], # 还原为经典竖直形态
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
        """更新移动计时器"""
        for direction in self.move_timers:
            if self.move_active[direction]:
                self.move_timers[direction] -= dt
    
    def check_gamepad_trigger(self, joystick, buttons, axis_config=None):
        """
        检查手柄按键是否触发（边沿检测）
        
        Args:
            joystick: pyglet 手柄对象
            buttons: 按钮编号列表
            axis_config: 可选的轴配置 (轴名称, 阈值, 是否大于)
        
        Returns:
            bool: 是否在本帧触发
        """
        is_pressed = False
        
        try:
            # 检查物理按钮
            is_pressed = any(
                b < len(joystick.buttons) and joystick.buttons[b] 
                for b in buttons
            )
            
            # 检查摇杆/十字键
            if not is_pressed and axis_config:
                axis_name, threshold, greater_than = axis_config
                axis_value = getattr(joystick, axis_name, 0)
                is_pressed = (axis_value > threshold) if greater_than else (axis_value < threshold)
        except:
            pass
        
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
        # 探测 Retina 缩放比例
        self.pixel_ratio = self._detect_pixel_ratio()
        
        # 计算窗口尺寸
        logical_width = GAME_COLS * GRID_SIZE + SIDEBAR_WIDTH + PADDING * 2
        logical_height = GAME_ROWS * GRID_SIZE + PADDING * 2
        
        super().__init__(
            width=logical_width,
            height=logical_height,
            caption='经典俄罗斯方块 | Modern Tetris',
            resizable=False
        )
        
        # 物理像素尺寸
        self.physical_width = self.width
        self.physical_height = self.height
        
        # 缩放后的物理像素级尺寸
        self.grid_size = int(GRID_SIZE * self.pixel_ratio)
        self.padding = int(PADDING * self.pixel_ratio)
        self.sidebar_width = int(SIDEBAR_WIDTH * self.pixel_ratio)
        
        # 游戏状态初始值（UI 布局依赖这些值）
        self.selected_level = 1
        self.hold_enabled = False      # 暂存默认关闭
        self.ui_time = 0.0
        self.reset_hold_timer = 0.0
        self.is_paused = False
        self.is_game_over = True
        
        # === 演示模式相关 ===
        self.idle_timer = 0.0          # 静置计时器
        self.idle_threshold = 15.0     # 15秒无操作进入演示模式
        self.demo_mode = False         # 演示模式标志
        self.demo_target_score = 0  # 0 表示没有分数限制，开启无尽刷分模式
        self.demo_ai_delay = 0.0       # AI决策延迟计时器
        self.demo_ai_action = None     # AI当前决策动作
        self.demo_ai_step = 0          # AI执行步骤计数
        self.demo_ai_target_info = None # (x, y, matrix)
        self.ai_conservative_mode = False # AI 策略状态：False 为大师模式，True 为保守模式
        
        # AI启发式权重（V14.0 - 狂暴进攻、地基解封策略）
        self.ai_weights = {
            'aggregate_height': -2.5,       # 狂暴模式：极速压水位
            'complete_lines': 5.0,
            'row_completeness': 150.0,   
            'holes': -50000.0,           
            'effective_well_value': 1500.0, 
            'no_right_pillar': -5000.0,     # 地基不足 6 层时严守，达标后直接重赏
            'base_flatness': -600.0,        
            'landing_depth': 25.0        
        } 

        # 初始化子系统
        self.input_handler = InputHandler()
        self.joysticks = self._initialize_joysticks()
        self._initialize_fonts()
        self._initialize_audio()
        self._initialize_graphics()
        
        self.reset_game(self.selected_level)
        self.is_game_over = True  # 启动时显示准备界面
        
        # 启动主循环
        pyglet.clock.schedule_interval(self.update, 1/60.0)
    
    def _detect_pixel_ratio(self):
        """探测 Retina 显示器的像素缩放比例"""
        try:
            temp_window = pyglet.window.Window(visible=False)
            ratio = temp_window.get_pixel_ratio()
            temp_window.close()
            return ratio
        except:
            return 1.0
    
    def _initialize_joysticks(self):
        """初始化手柄"""
        joysticks = []
        try:
            for joystick in pyglet.input.get_joysticks():
                joystick.open()
                joysticks.append(joystick)
        except:
            pass
        return joysticks
    
    def _initialize_fonts(self):
        """初始化字体系统"""
        # 尝试加载自定义字体
        script_dir = os.path.dirname(os.path.abspath(__file__))
        font_path = os.path.join(script_dir, 'fonts', 'Sarasa-Regular.ttc')
        
        if os.path.exists(font_path):
            try:
                pyglet.font.add_file(font_path)
                self.font_name = 'Sarasa UI SC'
            except:
                self.font_name = 'sans-serif'
        else:
            self.font_name = 'sans-serif'
        
        # 字体大小（物理像素）
        R = self.pixel_ratio
        self.font_size_large = int(28 * R)
        self.font_size_main = int(20 * R)
        self.font_size_small = int(11 * R)
        self.font_size_hint = int(10 * R)
    
    def _initialize_audio(self):
        """初始化音效系统"""
        self.sound_effects = {}
        self.active_sound_players = []
        self._generate_sound_effects()
    
    def _generate_sound_effects(self):
        """生成悦耳的合成音效"""
        sample_rate = 44100
        
        # 音效定义：[(频率, 时长, 音量), ...]
        # 特殊格式：('sweep', 起始频率, 结束频率, 时长, 音量)
        sound_definitions = {
            'move': [(1319, 0.035, 0.15)],
            'rotate': [(523, 0.035, 0.2), (784, 0.045, 0.22)],
            'lock': [(131, 0.05, 0.2)],
            'drop': [('sweep', 784, 131, 0.08, 0.25)],
            'clear': [
                (523, 0.06, 0.22), (659, 0.06, 0.22),
                (784, 0.06, 0.24), (1047, 0.12, 0.26)
            ],
            'levelup': [
                (523, 0.08, 0.2), (0, 0.015, 0),
                (587, 0.08, 0.2), (0, 0.015, 0),
                (659, 0.08, 0.22), (0, 0.015, 0),
                (784, 0.08, 0.22), (0, 0.015, 0),
                (1047, 0.16, 0.25)
            ],
            'gameover': [
                (659, 0.22, 0.2), (0, 0.04, 0),
                (523, 0.22, 0.18), (0, 0.04, 0),
                (440, 0.22, 0.16), (0, 0.04, 0),
                (330, 0.4, 0.18)
            ]
        }
        
        for name, notes in sound_definitions.items():
            samples = self._synthesize_notes(notes, sample_rate)
            wav_buffer = self._create_wav_buffer(samples, sample_rate)
            self.sound_effects[name] = pyglet.media.load(
                'sfx.wav', file=wav_buffer, streaming=False
            )
    
    def _synthesize_notes(self, notes, sample_rate):
        """合成一系列音符"""
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
        """核心振荡器：支持正弦波、三角波、方波 (buzz: 0-1) 和 纯噪声 (buzz > 1.5)"""
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
        """ADSR 包络生成器"""
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
        """创建 WAV 格式的音频缓冲区"""
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(struct.pack(f'<{len(samples)}h', *samples))
        buffer.seek(0)
        return buffer
    
    def play_sound(self, sound_name):
        """播放音效（带自动清理和限制）"""
        # 清理已播放完毕的音效
        try:
            self.active_sound_players = [
                player for player in self.active_sound_players 
                if player.playing
            ]
        except:
            self.active_sound_players = []
        
        # 限制最大同时播放数量，防止内存泄漏
        if len(self.active_sound_players) >= 50:
            return
        
        if sound_name in self.sound_effects:
            try:
                player = self.sound_effects[sound_name].play()
                self.active_sound_players.append(player)
            except:
                pass
    
    def _initialize_graphics(self):
        """初始化图形系统"""
        # 创建渲染批次
        self.batch_background = pyglet.graphics.Batch()
        self.batch_grid = pyglet.graphics.Batch()
        self.batch_arena = pyglet.graphics.Batch()
        self.batch_active_piece = pyglet.graphics.Batch()
        self.batch_ui = pyglet.graphics.Batch()
        self.batch_particles = pyglet.graphics.Batch()
        self.batch_overlay = pyglet.graphics.Batch()
        
        # 创建渲染组（解决 Z-Order 问题）
        self.ui_group_background = pyglet.graphics.Group(order=0)
        self.ui_group_foreground = pyglet.graphics.Group(order=1)
        
        self._create_ui_elements()
    
    def _create_ui_elements(self):
        """创建所有 UI 元素"""
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
        
        # === 网格线 ===
        self.grid_lines = []
        grid_color = (35, 45, 65)
        
        for x in range(GAME_COLS + 1):
            px = P + x * G
            line = shapes.Line(
                px, self.flip_y(P), px, self.flip_y(P + game_area_height),
                color=grid_color, batch=self.batch_grid
            )
            self.grid_lines.append(line)
        
        for y in range(GAME_ROWS + 1):
            py = self.flip_y(P + y * G)
            line = shapes.Line(
                P, py, P + game_area_width, py,
                color=grid_color, batch=self.batch_grid
            )
            self.grid_lines.append(line)
        
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
        """创建侧边栏 UI"""
        G, P, R = grid_size, padding, ratio
        
        # 侧边栏基础物理参数
        sidebar_x = P + game_area_width + int(24 * R)
        box_width = int(180 * R)
        box_height_preview = int(145 * R)
        box_height_stat = int(82 * R)
        separator = int(16 * R)
        label_padding_x = int(18 * R)
        label_padding_y = int(22 * R)

        # 保存为实例属性供动态布局重算
        self.sidebar_x = sidebar_x
        self.box_width = box_width
        self.box_height_preview = box_height_preview
        self.box_height_stat = box_height_stat
        self.separator = separator
        self.label_padding_x = label_padding_x
        self.label_padding_y = label_padding_y
        self.R = R
        self.P = P
        
        # 1. 创建预览方块池
        self.hold_piece_rects = [
            shapes.Rectangle(0, 0, G - 1, G - 1, batch=self.batch_ui, group=self.ui_group_foreground)
            for _ in range(16)
        ]
        self.next_piece_rects = [
            shapes.Rectangle(0, 0, G - 1, G - 1, batch=self.batch_ui, group=self.ui_group_foreground)
            for _ in range(16)
        ]
        for rect in self.hold_piece_rects + self.next_piece_rects:
            rect.visible = False

        # 2. 创建背景盒子 (初始位置在 0, 会被布局方法修正)
        corner_radius = int(10 * R)
        self.sidebar_boxes = [
            shapes.RoundedRectangle(sidebar_x, 0, box_width, box_height_preview, radius=corner_radius,
                color=(*CARD_BG, 180), batch=self.batch_ui, group=self.ui_group_background),
            shapes.RoundedRectangle(sidebar_x, 0, box_width, box_height_preview, radius=corner_radius,
                color=(*CARD_BG, 180), batch=self.batch_ui, group=self.ui_group_background),
            shapes.RoundedRectangle(sidebar_x, 0, box_width, box_height_stat, radius=corner_radius,
                color=(*CARD_BG, 180), batch=self.batch_ui, group=self.ui_group_background),
            shapes.RoundedRectangle(sidebar_x, 0, box_width, box_height_stat, radius=corner_radius,
                color=(*CARD_BG, 180), batch=self.batch_ui, group=self.ui_group_background),
            shapes.RoundedRectangle(sidebar_x, 0, box_width, int(box_height_stat * 1.5), radius=corner_radius,
                color=(*CARD_BG, 180), batch=self.batch_ui, group=self.ui_group_background)
        ]
        
        # 3. 创建文字标签
        self.labels = {
            'next': text.Label("下一个", font_name=self.font_name, font_size=self.font_size_small,
                color=(*TEXT_GREY, 255), x=sidebar_x + label_padding_x, y=0,
                batch=self.batch_ui, group=self.ui_group_foreground),
            'hold': text.Label("暂存", font_name=self.font_name, font_size=self.font_size_small,
                color=(*TEXT_GREY, 255), x=sidebar_x + label_padding_x, y=0,
                batch=self.batch_ui, group=self.ui_group_foreground),
            'score_title': text.Label("得分", font_name=self.font_name, font_size=self.font_size_small,
                color=(*TEXT_GREY, 255), x=sidebar_x + label_padding_x, y=0,
                batch=self.batch_ui, group=self.ui_group_foreground),
            'score_value': text.Label("0", font_name=self.font_name, font_size=self.font_size_main,
                weight='bold', color=(*PRIMARY_COLOR, 255), x=sidebar_x + label_padding_x, y=0,
                anchor_y='top', batch=self.batch_ui, group=self.ui_group_foreground),
            'level_title': text.Label("等级", font_name=self.font_name, font_size=self.font_size_small,
                color=(*TEXT_GREY, 255), x=sidebar_x + label_padding_x, y=0,
                batch=self.batch_ui, group=self.ui_group_foreground),
            'level_value': text.Label("1", font_name=self.font_name, font_size=self.font_size_main,
                weight='bold', color=(*PRIMARY_COLOR, 255), x=sidebar_x + label_padding_x, y=0,
                anchor_y='top', batch=self.batch_ui, group=self.ui_group_foreground),
            
            # 技术统计
            'stat_title': text.Label("技术统计", font_name=self.font_name, font_size=self.font_size_small,
                color=(*TEXT_GREY, 255), x=sidebar_x + label_padding_x, y=0,
                batch=self.batch_ui, group=self.ui_group_foreground),
            'stat_1': text.Label("单行: 0", font_name=self.font_name, font_size=int(10 * R),
                color=(255, 255, 255, 200), x=sidebar_x + label_padding_x, y=0,
                batch=self.batch_ui, group=self.ui_group_foreground),
            'stat_2': text.Label("双行: 0", font_name=self.font_name, font_size=int(10 * R),
                color=(255, 255, 255, 200), x=sidebar_x + label_padding_x, y=0,
                batch=self.batch_ui, group=self.ui_group_foreground),
            'stat_3': text.Label("三行: 0", font_name=self.font_name, font_size=int(10 * R),
                color=(255, 255, 255, 200), x=sidebar_x + label_padding_x, y=0,
                batch=self.batch_ui, group=self.ui_group_foreground),
            'stat_4': text.Label("四行: 0", font_name=self.font_name, font_size=int(10 * R),
                weight='bold', color=(251, 146, 60, 255), x=sidebar_x + label_padding_x, y=0,
                batch=self.batch_ui, group=self.ui_group_foreground),
        }
        
        # 生成提示信息（初次调用布局方法会处理位置）
        self.hints = [
            ("方向键", "移动 & 旋转"),
            ("空格", "硬降落"),
            ("C/Shift", "暂存"),
            ("P / R", "暂停 / 重置")
        ]
        self.hint_labels = []
        for i, (key_text, action_text) in enumerate(self.hints):
            kl = text.Label("", font_name=self.font_name, font_size=self.font_size_hint,
                           weight='bold', color=(255, 255, 255, 255),
                           batch=self.batch_ui, group=self.ui_group_foreground)
            al = text.Label("", font_name=self.font_name, font_size=self.font_size_hint,
                           color=(*TEXT_GREY, 255),
                           batch=self.batch_ui, group=self.ui_group_foreground)
            self.hint_labels.extend([kl, al])

        self._update_sidebar_layout() # 应用最终坐标
        
    def _update_sidebar_layout(self):
        """核心：动态重算侧边栏布局坐标"""
        P, R = self.P, self.R
        sep = self.separator
        hb, hs = self.box_height_preview, self.box_height_stat
        
        # 核心：根据 Hold 是否启用来分支计算
        self.offset_next = P
        if self.hold_enabled:
            self.offset_hold = self.offset_next + hb + sep
            self.offset_score = self.offset_hold + hb + sep
        else:
            self.offset_hold = -1000 # 移到屏幕外
            self.offset_score = self.offset_next + hb + sep
        
        self.offset_level = self.offset_score + hs + sep
        self.offset_stats = self.offset_level + hs + sep
        
        # 1. 更新盒子位置 (sidebar_boxes: [Next, Hold, Score, Level, Stats])
        if hasattr(self, 'sidebar_boxes'):
            self.sidebar_boxes[0].y = self.flip_y(self.offset_next + hb)
            self.sidebar_boxes[1].y = self.flip_y(self.offset_hold + hb)
            self.sidebar_boxes[1].visible = self.hold_enabled
            self.sidebar_boxes[2].y = self.flip_y(self.offset_score + hs)
            self.sidebar_boxes[3].y = self.flip_y(self.offset_level + hs)
            self.sidebar_boxes[4].y = self.flip_y(self.offset_stats + int(hs * 1.5))

        # 2. 更新文字标签位置
        if hasattr(self, 'labels'):
            lx, ly = self.label_padding_x, self.label_padding_y
            self.labels['next'].y = self.flip_y(self.offset_next + ly)
            self.labels['hold'].y = self.flip_y(self.offset_hold + ly)
            self.labels['hold'].visible = self.hold_enabled
            
            self.labels['score_title'].y = self.flip_y(self.offset_score + ly)
            self.labels['score_value'].y = self.flip_y(self.offset_score + ly + int(26 * R))
            self.labels['level_title'].y = self.flip_y(self.offset_level + ly)
            self.labels['level_value'].y = self.flip_y(self.offset_level + ly + int(26 * R))
            
            # 技术统计布局
            sy = self.offset_stats + ly
            lh = int(18 * R)
            self.labels['stat_title'].y = self.flip_y(sy)
            self.labels['stat_1'].y = self.flip_y(sy + lh + int(4 * R))
            self.labels['stat_2'].y = self.flip_y(sy + lh * 2 + int(4 * R))
            self.labels['stat_3'].y = self.flip_y(sy + lh * 3 + int(4 * R))
            self.labels['stat_4'].y = self.flip_y(sy + lh * 4 + int(4 * R))
            
        # 3. 更新操作提示 (弹性位移)
        if hasattr(self, 'hint_labels') and self.hint_labels:
            hint_y = self.offset_stats + int(hs * 1.5) + int(28 * R)
            line_h = int(19 * R)
            for i in range(len(self.hints)):
                # Key label
                self.hint_labels[i*2].x = self.sidebar_x + int(5 * R)
                self.hint_labels[i*2].y = self.flip_y(hint_y + i * line_h)
                self.hint_labels[i*2].text = self.hints[i][0]
                # Action label
                self.hint_labels[i*2+1].x = self.sidebar_x + int(54 * R)
                self.hint_labels[i*2+1].y = self.flip_y(hint_y + i * line_h)
                self.hint_labels[i*2+1].text = self.hints[i][1]
    
    def flip_y(self, game_y):
        """将游戏坐标转换为屏幕坐标（Y 轴翻转）"""
        return self.physical_height - game_y
    
    # ===== AI 演示模式核心算法 =====
    
    def ai_evaluate_board(self, test_arena, lines_cleared, is_high_risk, landing_y=None):
        """
        至尊大师级评估算法 (V6.5) - 13+1 策略 & 低区优先原则
        """
        cols = len(test_arena[0])
        rows = len(test_arena)
        
        col_heights = []
        for x in range(cols):
            h = 0
            for y in range(rows):
                if test_arena[y][x]:
                    h = rows - y
                    break
            col_heights.append(h)
        
        # --- 全局核心指标 (V13.1 稳定版) ---
        max_h = max(col_heights)
        main_well_col = cols - 1
        row_transitions = 0
        for y in range(rows):
            for x in range(cols - 1):
                if (test_arena[y][x] > 0) != (test_arena[y][x+1] > 0):
                    row_transitions += 1
            if test_arena[y][0] == 0: row_transitions += 1
            if test_arena[y][cols-1] == 0: row_transitions += 1

        col_transitions = 0
        for x in range(cols):
            for y in range(rows - 1):
                if (test_arena[y][x] > 0) != (test_arena[y+1][x] > 0):
                    col_transitions += 1
            if test_arena[rows-1][x] == 0: col_transitions += 1

        # 2. 空洞与遮盖 (杜绝遮盖空隙，违者重罚)
        holes = 0
        blocks_above_holes = 0
        for x in range(cols):
            block_count_in_col = 0
            for y in range(rows):
                if test_arena[y][x] > 0:
                    block_count_in_col += 1
                elif block_count_in_col > 0:
                    holes += 1
                    # 每一层遮盖都是致命的
                    blocks_above_holes += block_count_in_col
        
        # 3. 经典 9+1 策略
        wells = []
        for x in range(cols):
            # 井的定义：左右都比自己高
            l = col_heights[x-1] if x > 0 else rows 
            r = col_heights[x+1] if x < cols - 1 else rows
            d = min(l, r) - col_heights[x]
            if d > 0:
                wells.append((d, x))
        
        well_penalty = 0
        right_well_reward = 0
        
        # 3.1 提取左侧区域高度（13列）
        left_heights = [col_heights[i] for i in range(main_well_col)]
        left_max = max(left_heights) if left_heights else 0
        left_min = min(left_heights) if left_heights else 0

        # 3.0 预计算左侧完整行数，作为战术解锁和蓄力的依据
        left_full_rows = 0
        for y in range(rows):
            is_row_complete = True
            for x in range(main_well_col):
                if test_arena[y][x] == 0:
                    is_row_complete = False
                    break
            if is_row_complete:
                left_full_rows += 1

        if is_high_risk:
            # 危机模式：全力求生，惩罚所有井，包括右侧
            well_penalty = sum(w[0] for w in wells) * 1000.0
        else:
            # 正常模式：实施 13+1 策略 (左侧平整地基 + 右侧有效深井)
            
            # 这里的 wells 是通用的井列表。我们需要专门处理最右侧
            h13 = col_heights[main_well_col - 1]
            h14 = col_heights[main_well_col]
            
            # 狂暴进攻判定：左侧最高点超过 6 层即视为解禁
            emergency_mode = (left_max > 6)
            
            if h13 > h14:
                # 合法井：右侧第 14 列低于第 13 列
                depth = h13 - h14
                effective_d = min(depth, left_max + 1)
                right_well_reward += (effective_d ** 2) * 20000.0 + 100000.0
            elif h14 > h13:
                # 狂暴逻辑：在 6 层以上开启“无脑下竖条”模式
                if left_full_rows < 6 and not emergency_mode:
                    # 只有在极低位且没打好地基时，才严禁破坏井位
                    well_penalty += (h14 - h13) * 400000.0
                else:
                    # 狂暴重赏：500万分起步！让 AI 迷恋右侧冒尖带来的泄洪感
                    right_well_reward += (h14 - h13) * 200000.0 + 5000000.0

            # 处理其他位置的杂井 (左侧 13 列必须铁板一块)
            for d, x in wells:
                if x != main_well_col:
                    well_penalty += (d ** 2) * 100000.0

            # 3.1b 检查井口是否被堵 (非紧急模式下更严厉)
            if left_heights:
                min_left_h = min(left_heights)
                if col_heights[main_well_col] > min_left_h + 2:
                     penalty_factor = 10000.0 if not emergency_mode else 1000.0
                     well_penalty += (col_heights[main_well_col] - min_left_h) * penalty_factor

        # 3.2 行完整度 (保整行) - 核心算法：通过统计行内列填充数给予平方级奖励
        row_integrity_bonus = 0
        for y in range(rows):
            row_blocks = 0
            for x in range(main_well_col):
                if test_arena[y][x] > 0:
                    row_blocks += 1
            if row_blocks > 0:
                # 海量奖励：13个块的行奖励将达到 169 * 1000 = 16.9 万分
                # 迫使 AI 疯狂想要“平推”左侧，消灭这种由于局部冒尖带来的地基不稳。
                row_integrity_bonus += (row_blocks ** 2) * 1000.0

        # 3.3 地基平整度与修复惩罚 (确保 13 列整体平推)
        low_point_penalty = 0
        if left_heights:
            max_h_left = max(left_heights)
            min_h_left = min(left_heights)
            
            # 门槛从 3 降到 1：只要有落差，就视为严重失误
            if max_h_left - min_h_left > 1:
                low_point_penalty += (max_h_left - min_h_left) * 50000.0

            for x, h in enumerate(left_heights):
                if h < max_h_left:
                    gap_depth = max_h_left - h
                    # 极速填坑动力
                    low_point_penalty += (gap_depth ** 2) * 30000.0

        # 3.4 蓄力策略 (Stack Building)
        stack_building_penalty = 0
        if 0 < lines_cleared < 4 and left_full_rows < 3:
            # 只有在非危险状态且处于 6 层以下安全水位时才限制消行。
            if not is_high_risk and not (max_h > 6):
                # 高达 80 万分的罚款，足以封杀一切非 4 行的消行意图，强迫补齐左侧。
                stack_building_penalty = 800000.0

        # 3.5 凹凸度 (Bumpiness) - 维持局部微观平滑
        left_bumpiness = 0
        for x in range(main_well_col - 1):
            diff = abs(col_heights[x] - col_heights[x+1])
            left_bumpiness += diff * diff 

        # 4. 消行奖励 - 诱导 4 行
        if is_high_risk:
            line_bonus = {0:0, 1:20000, 2:50000, 3:120000, 4:400000}[lines_cleared]
        else:
            # 大师模式：极度渴望 4 行
            # 如果消的是 1-3 行，且目前右侧井还没攒够，给予轻微负分以示警告
            line_bonus = {0:0, 1:-5000, 2:5000, 3:20000, 4:1000000}[lines_cleared]

        # 5. 综合评分
        agg_h = sum(col_heights)
        max_h = max(col_heights)
        h_penalty = 60.0 if is_high_risk else 1.0
        
        # 6. 深度优先重力 (Landing Depth)
        # landing_y 越大表示落点越靠下。
        landing_penalty = 0
        if landing_y is not None:
            # 维持适度引导，将机会留给完美的 shapes
            landing_penalty = (rows - landing_y) * 200.0

        score = (
            line_bonus 
            + right_well_reward
            + row_integrity_bonus
            - (agg_h * 60.0 * h_penalty)   
            - (row_transitions * 3000.0)    # 提升咬合度要求，减少细碎缝隙
            - (col_transitions * 3000.0) 
            - (left_bumpiness * 300.0)      
            - (low_point_penalty)           
            - (stack_building_penalty)      
            - (holes * 5000000.0 * h_penalty) # 终极禁令：500万分惩罚，空洞即破产
            - (blocks_above_holes * 500000.0) # 严重惩罚遮盖，根除颗粒空洞
            - well_penalty
            - (max_h * 800.0 * h_penalty)
            - landing_penalty
        )
        return score

    def ai_find_best_move(self):
        """AI寻找最佳落点 (极致二级搜索 V6.0)"""
        actual_h = 0
        for y in range(GAME_ROWS):
            if any(self.arena[y]):
                actual_h = GAME_ROWS - y
                break
        
        # 稍微调高恢复大师模式的门槛，确保彻底清理干净
        if actual_h > (GAME_ROWS * 0.5):
            self.ai_conservative_mode = True
        elif actual_h < 6:
            self.ai_conservative_mode = False
            
        current_mode = self.ai_conservative_mode
        
        # --- 第一层搜索：评估所有可用方块 (当前 vs 暂存) ---
        candidates = []
        # 选项 A: 使用当前方块
        candidates.append({'mat': self.current_piece_matrix, 'hold': False})
        
        # 选项 B: 考虑使用暂存区
        if self.hold_enabled and self.can_hold:
            if self.hold_piece_type is not None:
                hold_mat = [row[:] for row in SHAPES[self.hold_piece_type]]
                candidates.append({'mat': hold_mat, 'hold': True})
            else:
                # 暂存区为空，暂存当前会使用下一个方块
                next_mat = [row[:] for row in SHAPES[self.next_piece_type]]
                candidates.append({'mat': next_mat, 'hold': True})

        scored_moves1 = []
        for cand in candidates:
            m_base = cand['mat']
            for rot1 in range(4):
                m1 = m_base
                for _ in range(rot1):
                    m1 = [list(row) for row in zip(*m1[::-1])]
                
                for x1 in range(-2, GAME_COLS + 2):
                    if not self._check_collision_static(self.arena, {'x': x1, 'y': 0}, m1):
                        y1 = 0
                        while not self._check_collision_static(self.arena, {'x': x1, 'y': y1+1}, m1):
                            y1 += 1
                        
                        arena1, clear1 = self._simulate_placement(self.arena, x1, y1, m1)
                        s1 = self.ai_evaluate_board(arena1, clear1, current_mode, landing_y=y1)
                        scored_moves1.append((s1, rot1, x1, y1, m1, arena1, cand['hold']))
        
        scored_moves1.sort(key=lambda x: x[0], reverse=True)
        
        # --- 第二层搜索 (增强采样) ---
        best_overall_score = float('-inf')
        final_rot, final_x, final_y, final_mat = 0, 0, 0, None
        final_hold = False
        
        search_limit = 32
        for s1, rot1, x1, y1, mat1, arena1, is_hold in scored_moves1[:search_limit]:
            best_s2 = float('-inf')
            
            # 第二层总是使用剩下的“下一个”块
            # 如果第一层选了 hold 且 hold 原本就有块，那么第二层用 current
            # 如果第一层选了 hold 且 hold 原本没块，那么第二层用 next_next (简化处理：仍用 next)
            # 如果第一层没选 hold，那么第二层用 next
            m2_base = self.next_piece_matrix
            if is_hold and self.hold_piece_type is not None:
                # 这种情况其实有点复杂，为了性能，我们简化：第二层统一看 next_piece
                pass

            for rot2 in range(4):
                m2 = m2_base
                for _ in range(rot2):
                    m2 = [list(row) for row in zip(*m2[::-1])]
                
                for x2 in range(-2, GAME_COLS + 2):
                    if not self._check_collision_static(arena1, {'x': x2, 'y': 0}, m2):
                        y2 = 0
                        while not self._check_collision_static(arena1, {'x': x2, 'y': y2+1}, m2):
                            y2 += 1
                        arena2, clear2 = self._simulate_placement(arena1, x2, y2, m2)
                        s2 = self.ai_evaluate_board(arena2, clear2, current_mode, landing_y=y2)
                        if s2 > best_s2:
                            best_s2 = s2
            
            total_s = s1 + best_s2
            if total_s > best_overall_score:
                best_overall_score = total_s
                final_rot, final_x, final_y, final_mat = rot1, x1, y1, mat1
                final_hold = is_hold
        
        if not final_mat and scored_moves1:
            # 安全降级：如果没有找到两层搜索的最佳解，取第一层搜索的最佳解
            s1, final_rot, final_x, final_y, final_mat, _, final_hold = scored_moves1[0]
            best_overall_score = s1

        return final_rot, final_x, best_overall_score, final_y, final_mat, final_hold

    def _simulate_placement(self, arena, piece_x, piece_y, matrix):
        """模拟放置并返回 (新棋盘, 消行数)"""
        new_arena = [row[:] for row in arena]
        for y, row in enumerate(matrix):
            for x, val in enumerate(row):
                if val:
                    ay, ax = piece_y + y, piece_x + x
                    if 0 <= ay < GAME_ROWS and 0 <= ax < GAME_COLS:
                        new_arena[ay][ax] = val
        
        # 计算并清除满行
        original_rows = len(new_arena)
        new_arena = [row for row in new_arena if not all(row)]
        cleared = original_rows - len(new_arena)
        
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
    
    def ai_execute_move(self, target_rotation, target_x, should_hold=False):
        """AI执行移动到目标位置的动作序列"""
        if self.demo_ai_action is None:
            # 初始化动作序列
            actions = []
            
            # 0. 如果策略决定使用暂存方块，先执行 hold
            if should_hold:
                actions.append('hold')
            
            # 1. 旋转到目标角度
            current_rotation = 0  # 简化：假设从0开始
            rotations_needed = target_rotation
            for _ in range(rotations_needed):
                actions.append('rotate')
            
            # 2. 水平移动
            current_x = self.piece_position['x']
            dx = target_x - current_x
            
            if dx > 0:
                for _ in range(abs(dx)):
                    actions.append('right')
            elif dx < 0:
                for _ in range(abs(dx)):
                    actions.append('left')
            
            # 3. 硬降落
            actions.append('drop')
            
            self.demo_ai_action = actions
            self.demo_ai_step = 0
        
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
            elif action == 'drop':
                self.hard_drop()
                self.demo_ai_action = None  # 完成一次完整操作
                self.demo_ai_step = 0
                return True  # 表示完成
            
            self.demo_ai_step += 1
        
        return False  # 还在执行中
    
    def enter_demo_mode(self):
        """进入演示模式"""
        self.demo_mode = True
        self.reset_game(self.selected_level)
        self.demo_ai_delay = 0.0
        self.demo_ai_action = None
        self.demo_ai_step = 0
        self.demo_ai_target_info = None
    
    def exit_demo_mode(self):
        """退出演示模式"""
        self.demo_mode = False
        self.idle_timer = 0.0
        self.is_game_over = True  # 让玩家选择是否开始新游戏
    
    def reset_game(self, start_level=1):
        """重置游戏状态"""
        self.arena = [[0] * GAME_COLS for _ in range(GAME_ROWS)]
        self.score = 0
        self.level = start_level
        self.lines_cleared = 0
        
        # 消行技术统计
        self.line_stats = {1: 0, 2: 0, 3: 0, 4: 0}
        
        # 7-Bag 初始化
        self.bag = self._fill_bag()
        self.next_piece_type = self._get_next_from_bag()
        self.next_piece_matrix = self._get_initial_matrix(self.next_piece_type)
        
        # 锁定延迟参数 (Lock Delay)
        self.lock_delay_timer = 0
        self.lock_delay_limit = 0.5   # 标准 0.5 秒落地喘息时间
        self.max_lock_resets = 15      # 防止无限旋转滑行
        self.lock_delay_moves = 0
        
        self.drop_counter = 0
        self.hold_piece_type = None
        self.can_hold = True
        
        self.particles = []
        self.is_paused = False
        self.is_game_over = False
        self.is_on_ground = False
        self.lock_timer = 0
        self.spawn_piece()
    
    def _get_initial_matrix(self, piece_type):
        """获取方块的初始矩阵，针对 I 形增加随机横竖形态"""
        matrix = [row[:] for row in SHAPES[piece_type]]
        if piece_type == 'I' and random.random() < 0.5:
            # 执行 90 度旋转变为横向
            matrix = [[matrix[y][x] for y in range(len(matrix))] for x in range(len(matrix[0]))]
            for row in matrix: row.reverse()
        return matrix

    def _fill_bag(self):
        """7-Bag 随机算法：确保 7 个一组，每组必含所有种类"""
        types = list(SHAPES.keys())
        random.shuffle(types)
        return types

    def _get_next_from_bag(self):
        """从口袋里抽下一个块，抽完自动补货"""
        if not self.bag:
            self.bag = self._fill_bag()
        return self.bag.pop()

    def spawn_piece(self):
        """生成新方块"""
        self.current_piece_type = self.next_piece_type
        self.current_piece_matrix = self.next_piece_matrix
        
        # 清除演示模式的目标信息
        if self.demo_mode:
            self.demo_ai_target_info = None
        
        # 7-Bag 抽签
        self.next_piece_type = self._get_next_from_bag()
        self.next_piece_matrix = self._get_initial_matrix(self.next_piece_type)
        
        self.piece_position = {
            'x': GAME_COLS // 2 - len(self.current_piece_matrix[0]) // 2,
            'y': 0
        }
        
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
        """检查碰撞"""
        for y, row in enumerate(matrix):
            for x, value in enumerate(row):
                if value:
                    arena_y = y + position['y']
                    arena_x = x + position['x']
                    
                    if (arena_y >= GAME_ROWS or 
                        arena_x < 0 or 
                        arena_x >= GAME_COLS or
                        (arena_y >= 0 and self.arena[arena_y][arena_x])):
                        return True
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
                    self.arena[arena_y][arena_x] = value
        
        self.spawn_piece()
        self.clear_lines()
        
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
        """消除满行（集成 T-Spin 全套奖励）"""
        lines_count = 0
        y = GAME_ROWS - 1
        
        while y >= 0:
            if 0 not in self.arena[y]:
                row_data = self.arena[y][:]
                self.create_line_clear_particles(y, row_data)
                self.arena.pop(y)
                self.arena.insert(0, [0] * GAME_COLS)
                lines_count += 1
            else:
                y -= 1
        
        if lines_count == 0:
            if self.t_spin_detected:
                # T-Spin 0 行也有 100 分
                self.score += 100
            return

        # 更新技术统计
        if lines_count in self.line_stats:
            self.line_stats[lines_count] += 1

        # 基础得分逻辑优化
        line_bonuses = {1: 100, 2: 300, 3: 500, 4: 800}
        t_spin_bonuses = {1: 800, 2: 1200, 3: 1600} # T-Spin 倍率极大
        
        if self.t_spin_detected:
            self.score += t_spin_bonuses.get(lines_count, 400) * self.level
            print(f"WOW! T-Spin {'Double' if lines_count==2 else 'Single' if lines_count==1 else 'Triple'}!")
        else:
            self.score += line_bonuses.get(lines_count, 0) * self.level
        
        self.lines_cleared += lines_count
        self.play_sound('clear')
        
        # 难度升级逻辑
        if self.score >= self.level * 1000: # 提高升级门槛，让 T-Spin 更有意义
            self.level += 1
            self.play_sound('levelup')
    
    def create_line_clear_particles(self, row_y, row_data):
        """创建消行粒子效果"""
        if len(self.particles) >= MAX_PARTICLES:
            return
        
        # 边界检查
        if row_y < 0 or row_y >= GAME_ROWS:
            return
        
        G = self.grid_size
        P = self.padding
        
        # 创建粒子，严格控制数量
        particles_to_add = []
        for x, value in enumerate(row_data):
            if value and len(self.particles) + len(particles_to_add) < MAX_PARTICLES:
                px = P + x * G + G // 2
                py = self.flip_y(P + row_y * G + G // 2)
                
                for _ in range(min(6, MAX_PARTICLES - len(self.particles) - len(particles_to_add))):
                    particles_to_add.append(Particle(px, py, COLORS[value]))
        
        # 批量添加，避免循环中修改列表
        self.particles.extend(particles_to_add)
    
    def get_ghost_position(self):
        """计算幽灵方块位置"""
        ghost_pos = {
            'x': self.piece_position['x'],
            'y': self.piece_position['y']
        }
        
        while not self.check_collision(ghost_pos, self.current_piece_matrix):
            ghost_pos['y'] += 1
        
        ghost_pos['y'] -= 1
        return ghost_pos
    
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
            except:
                pass
        
        # 手柄操作重置静置计时器
        if self.joysticks:
            js = self.joysticks[0]
            try:
                if any(js.buttons) or abs(getattr(js, 'x', 0)) > 0.3 or abs(getattr(js, 'y', 0)) > 0.3:
                    self.idle_timer = 0.0
            except:
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
            except: pass
            
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
        
        # 软降落（持续触发）
        try:
            if ((hasattr(joystick, 'y') and joystick.y > 0.5) or
                (hasattr(joystick, 'hat_y') and joystick.hat_y < -0.5)):
                self.move_piece_down()
        except:
            pass
        
        # 旋转（单次触发）- 按钮1/2 或 十字键上
        if self.input_handler.check_gamepad_trigger(joystick, [1, 2], ('hat_y', 0.5, True)):
            self.rotate_piece(1)
        
        # 硬降落（单次触发）- 仅按钮3
        if self.input_handler.check_gamepad_trigger(joystick, [3]):
            self.hard_drop()
        
        # 暂存（单次触发）
        if self.input_handler.check_gamepad_trigger(joystick, [4, 5]):
            self.hold_piece()
    
    def update_movement(self, dt):
        """更新移动输入（DAS/ARR）"""
        if self.is_paused or self.is_game_over:
            return
        
        # 键盘方向键
        key_left = key.LEFT in self.input_handler.keys_pressed
        key_right = key.RIGHT in self.input_handler.keys_pressed
        
        # 手柄方向输入
        gamepad_left = False
        gamepad_right = False
        
        if self.joysticks:
            try:
                joystick = self.joysticks[0]
                gamepad_left = (
                    (hasattr(joystick, 'x') and joystick.x < -0.5) or
                    (hasattr(joystick, 'hat_x') and joystick.hat_x < -0.5)
                )
                gamepad_right = (
                    (hasattr(joystick, 'x') and joystick.x > 0.5) or
                    (hasattr(joystick, 'hat_x') and joystick.hat_x > 0.5)
                )
            except:
                pass
        
        # 处理左右移动
        for direction, is_active, delta_x in [
            ('left', key_left or gamepad_left, -1),
            ('right', key_right or gamepad_right, 1)
        ]:
            if is_active:
                if not self.input_handler.move_active[direction]:
                    self.move_piece_horizontal(delta_x)
                    self.input_handler.move_timers[direction] = DAS_DELAY
                    self.input_handler.move_active[direction] = True
                elif self.input_handler.move_timers[direction] <= 0:
                    self.move_piece_horizontal(delta_x)
                    self.input_handler.move_timers[direction] = ARR_DELAY
            else:
                self.input_handler.move_active[direction] = False
    
    def _reset_lock_timer(self):
        """移动或旋转时重置锁定计时器"""
        if self.lock_delay_moves < self.max_lock_resets:
            self.lock_delay_timer = 0
            self.lock_delay_moves += 1

    def update(self, dt):
        """主更新循环"""
        self.ui_time += dt
        
        # 处理手柄输入和组合重置
        self.handle_gamepad_input(dt)
        
        # === 演示模式逻辑 ===
        if self.demo_mode:
            # 演示模式下，检查是否达到目标分数 (demo_target_score 为 0 表示没有限制)
            if self.demo_target_score > 0 and self.score >= self.demo_target_score:
                self.exit_demo_mode()
                return
            
            # 演示模式下Game Over自动重新开始
            if self.is_game_over:
                self.reset_game(self.selected_level)
                self.demo_ai_action = None
                return
            
            # AI自动玩游戏
            if not self.is_paused:
                self.demo_ai_delay += dt
                
                # AI执行延迟
                if self.demo_ai_delay >= 0.05:
                    self.demo_ai_delay = 0.0
                    
                    if self.demo_ai_action is None:
                        # 计算最佳移动，并尝试执行
                        best_rot, best_x, best_score, best_y, best_mat, should_hold = self.ai_find_best_move()
                        self.ai_execute_move(best_rot, best_x, should_hold)
                    else:
                        self.ai_execute_move(0, 0)
        else:
            # 非演示模式：静置检测
            if self.is_game_over:
                self.idle_timer += dt
                if self.idle_timer >= self.idle_threshold:
                    self.enter_demo_mode()
                    return
        
        # 更新移动输入（DAS/ARR）
        self.update_movement(dt)
        self.input_handler.update_move_timers(dt)
        
        # 游戏逻辑更新
        if not self.is_paused and not self.is_game_over:
            # 软降落键盘支持
            if key.DOWN in self.input_handler.keys_pressed:
                self.move_piece_down()
            
            # 锁定延迟核心逻辑
            # 探测：如果下一格会碰撞，说明已落地
            temp_pos = {'x': self.piece_position['x'], 'y': self.piece_position['y'] + 1}
            is_on_ground = self.check_collision(temp_pos, self.current_piece_matrix)
            
            if is_on_ground:
                self.lock_delay_timer += dt
                if self.lock_delay_timer >= self.lock_delay_limit:
                    self.lock_piece()
            else:
                # 只有在空中才计算自动下落
                self.drop_counter += dt
                # 基础下落速度随等级提升
                fall_speed = max(0.05, 1.0 * (0.9 ** (self.level - 1)))
                if self.drop_counter >= fall_speed:
                    self.drop_counter = 0
                    self.move_piece_down()
        
        # 更新粒子（安全更新）
        try:
            self.particles = [p for p in self.particles if p.update(dt)]
        except:
            self.particles = []
    
    def on_draw(self):
        """渲染循环"""
        self.clear()
        
        # 更新文字
        self.labels['score_value'].text = str(self.score)
        self.labels['level_value'].text = str(self.level)
        
        # 更新技术统计文字
        if hasattr(self, 'line_stats'):
            self.labels['stat_1'].text = f"单行: {self.line_stats[1]}"
            self.labels['stat_2'].text = f"双行: {self.line_stats[2]}"
            self.labels['stat_3'].text = f"三行: {self.line_stats[3]}"
            self.labels['stat_4'].text = f"四行: {self.line_stats[4]}"
        
        # 更新游戏区UI
        self.update_arena_ui()
        
        # 更新当前方块和幽灵方块
        if not self.is_game_over and not self.is_paused:
            self.update_ghost_piece_ui()
            self.update_active_piece_ui()
        else:
            for rect in (self.active_piece_rects + 
                        self.ghost_piece_rects + 
                        self.ghost_piece_outlines):
                rect.visible = False
        
        # 更新预览
        self.update_preview_ui()
        
        # 更新粒子
        self.update_particles_ui()
        
        # 更新叠加层
        if (self.is_paused or self.is_game_over) and not self.demo_mode:
            R = self.pixel_ratio
            if self.is_game_over:
                if self.score == 0:
                    self.overlay_title.text = "准  备  开  始"
                    self.overlay_title.color = (34, 197, 94, 255)  # 翡翠绿
                else:
                    self.overlay_title.text = "游  戏  结  束"
                    self.overlay_title.color = (244, 63, 94, 255) # 玫瑰红
                
                is_hard = self.selected_level > 1
                mode_str = "硬核模式 (Lv.100)" if is_hard else "普通模式"
                hold_str = "暂存: [开]" if self.hold_enabled else "暂存: [关]"
                self.overlay_mode.text = f"模式: {mode_str}  |  {hold_str}"
                self.overlay_mode.color = (251, 146, 60, 255) if is_hard else (45, 212, 191, 255) # 橙色 vs 青色
                
                self.overlay_hint.text = "[Select] 难度  |  [H/XY] 暂存  |  [Start] 开始"
                self.overlay_mode.visible = True
            else:
                self.overlay_title.text = "游  戏  暂  停"
                self.overlay_title.color = (56, 189, 248, 255) # 科技蓝
                self.overlay_mode.visible = False
                self.overlay_hint.text = "按下 P 键或功能键继续"
            
            # 动态调整容器尺寸
            box_cx = (self.padding + (GAME_COLS * self.grid_size) // 2)
            box_cy = self.flip_y(self.padding + (GAME_ROWS * self.grid_size) // 2)
            
            bw, bh = int(300 * R), int(180 * R)
            bx, by = box_cx - bw // 2, box_cy - bh // 2
            
            self.overlay_box_bg.x, self.overlay_box_bg.y = bx, by
            self.overlay_box_bg.width, self.overlay_box_bg.height = bw, bh
            
            # 边框呼吸动效
            pulse = (math.sin(self.ui_time * 3) + 1) / 2 # 0-1
            self.overlay_box_border.x, self.overlay_box_border.y = bx, by
            self.overlay_box_border.width, self.overlay_box_border.height = bw, bh
            self.overlay_box_border.color = (56, 189, 248, int(100 + pulse * 100))
            
            # 更新 L 型饰件 (Corner Brackets)
            al = int(15 * R) # 饰件长度
            # 左上
            self.overlay_accents[0].x, self.overlay_accents[0].y = bx, by + bh
            self.overlay_accents[0].x2, self.overlay_accents[0].y2 = bx + al, by + bh
            self.overlay_accents[1].x, self.overlay_accents[1].y = bx, by + bh
            self.overlay_accents[1].x2, self.overlay_accents[1].y2 = bx, by + bh - al
            # 右上
            self.overlay_accents[2].x, self.overlay_accents[2].y = bx + bw, by + bh
            self.overlay_accents[2].x2, self.overlay_accents[2].y2 = bx + bw - al, by + bh
            self.overlay_accents[3].x, self.overlay_accents[3].y = bx + bw, by + bh
            self.overlay_accents[3].x2, self.overlay_accents[3].y2 = bx + bw, by + bh - al
            # 左下
            self.overlay_accents[4].x, self.overlay_accents[4].y = bx, by
            self.overlay_accents[4].x2, self.overlay_accents[4].y2 = bx + al, by
            self.overlay_accents[5].x, self.overlay_accents[5].y = bx, by
            self.overlay_accents[5].x2, self.overlay_accents[5].y2 = bx, by + al
            # 右下
            self.overlay_accents[6].x, self.overlay_accents[6].y = bx + bw, by
            self.overlay_accents[6].x2, self.overlay_accents[6].y2 = bx + bw - al, by
            self.overlay_accents[7].x, self.overlay_accents[7].y = bx + bw, by
            self.overlay_accents[7].x2, self.overlay_accents[7].y2 = bx + bw, by + al
            
            self.overlay_title.position = (box_cx, box_cy + int(45 * R), 0)
            self.overlay_mode.position = (box_cx, box_cy + int(5 * R), 0)
            self.overlay_hint.position = (box_cx, box_cy - int(40 * R), 0)
            
            for acc in self.overlay_accents: acc.visible = True
            self.overlay_box_bg.visible = True
            self.overlay_box_border.visible = True
        else:
            self.overlay_box_bg.visible = False
            self.overlay_box_border.visible = False
            self.overlay_mode.visible = False
            self.overlay_title.text = ""  # 清除标题文字
            self.overlay_hint.text = ""   # 清除提示文字
            for acc in self.overlay_accents: acc.visible = False
        
        # 按顺序绘制
        self.batch_background.draw()
        self.batch_grid.draw()
        self.batch_arena.draw()
        self.batch_active_piece.draw()
        self.batch_particles.draw()
        self.batch_ui.draw()
        
        if self.is_paused or self.is_game_over or self.demo_mode:
            self.batch_overlay.draw()
    
    def update_arena_ui(self):
        """更新游戏区UI"""
        G = self.grid_size
        P = self.padding
        
        for y in range(GAME_ROWS):
            for x in range(GAME_COLS):
                value = self.arena[y][x]
                rect = self.arena_rectangles[y][x]
                border = self.arena_borders[y][x]
                
                if value:
                    px = P + x * G
                    grid_y = P + y * G
                    py = self.flip_y(grid_y + G)
                    
                    rect.x = px
                    rect.y = py
                    rect.color = COLORS[value]
                    rect.visible = True
                    
                    border.x = px
                    border.y = py + G - 1
                    border.x2 = px + G - 1
                    border.y2 = py + G - 1
                    border.visible = True
                else:
                    rect.visible = False
                    border.visible = False
    
    def update_active_piece_ui(self):
        """更新当前方块UI"""
        G = self.grid_size
        P = self.padding
        index = 0
        
        for y, row in enumerate(self.current_piece_matrix):
            for x, value in enumerate(row):
                if value and index < len(self.active_piece_rects):
                    px = P + (x + self.piece_position['x']) * G
                    grid_y = P + (y + self.piece_position['y']) * G
                    py = self.flip_y(grid_y + G)
                    
                    rect = self.active_piece_rects[index]
                    rect.x = px
                    rect.y = py
                    rect.color = COLORS[value]
                    rect.visible = True
                    index += 1
        
        for i in range(index, len(self.active_piece_rects)):
            self.active_piece_rects[i].visible = False
    
    def update_ghost_piece_ui(self):
        """更新幽灵方块UI"""
        G = self.grid_size
        P = self.padding
        ghost_pos = self.get_ghost_position()
        index = 0
        
        for y, row in enumerate(self.current_piece_matrix):
            for x, value in enumerate(row):
                if value and index < len(self.ghost_piece_rects):
                    px = P + (x + ghost_pos['x']) * G
                    grid_y = P + (y + ghost_pos['y']) * G
                    py = self.flip_y(grid_y + G)
                    
                    rect = self.ghost_piece_rects[index]
                    rect.x = px
                    rect.y = py
                    rect.color = (*CARD_BG, 100)
                    rect.visible = True
                    
                    outline = self.ghost_piece_outlines[index]
                    outline.x = px
                    outline.y = py
                    outline.color = (*COLORS[value], 180)
                    outline.visible = True
                    index += 1
        
        for i in range(index, len(self.ghost_piece_rects)):
            self.ghost_piece_rects[i].visible = False
            self.ghost_piece_outlines[i].visible = False
    
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
        """更新预览方块 - 修复坐标叠加并实现精确居中"""
        G = self.grid_size
        P = self.padding
        
        # 1. 扫描真实像素边界
        occupied = [(x, y) for y, row in enumerate(matrix) for x, v in enumerate(row) if v]
        if not occupied:
            for r in rect_pool: r.visible = False
            return

        min_x, max_x = min(c[0] for c in occupied), max(c[0] for c in occupied)
        min_y, max_y = min(c[1] for c in occupied), max(c[1] for c in occupied)
        real_w, real_h = max_x - min_x + 1, max_y - min_y + 1
        
        # 2. 计算居中偏差 (单位: units)
        # 注意：这里不再加 P，因为 y_offset 已经是基于窗口顶部的绝对逻辑位置
        total_w_units = self.box_width / G
        x_center_bias = (total_w_units - real_w) / 2 - min_x
        
        title_h_units = self.label_padding_y / G + 0.3
        total_h_units = self.box_height_preview / G
        y_center_bias = title_h_units + (total_h_units - title_h_units - real_h) / 2 - min_y
        
        # 绝对逻辑起点 (不依赖 P)
        abs_start_x = self.sidebar_x / G + x_center_bias
        abs_start_y = y_offset / G + y_center_bias
        
        # 3. 渲染
        index = 0
        for y, row in enumerate(matrix):
            for x, value in enumerate(row):
                if value and index < len(rect_pool):
                    # 直接映射物理像素位置
                    px = int((x + abs_start_x) * G)
                    gy = int((y + abs_start_y) * G)
                    py = self.flip_y(gy + G)
                    
                    rect = rect_pool[index]
                    rect.x = px
                    rect.y = py
                    rect.color = (*[int(c*0.4) for c in COLORS[value]], 255) if dimmed else COLORS[value]
                    rect.visible = True
                    index += 1
        
        for i in range(index, len(rect_pool)):
            rect_pool[i].visible = False
    
    def update_particles_ui(self):
        """更新粒子UI"""
        index = 0
        
        for particle in self.particles:
            if index < len(self.particle_rectangles):
                rect = self.particle_rectangles[index]
                rect.x = int(particle.x) - particle.size
                rect.y = int(particle.y) - particle.size
                rect.width = particle.size * 2
                rect.height = particle.size * 2
                rect.color = (*particle.color, max(0, min(255, int(particle.alpha))))
                rect.visible = True
                index += 1
        
        for i in range(index, len(self.particle_rectangles)):
            self.particle_rectangles[i].visible = False
    
    def on_close(self):
        """窗口关闭清理"""
        for joystick in self.joysticks:
            try:
                joystick.close()
            except:
                pass
        
        super().on_close()


if __name__ == "__main__":
    game = TetrisGame()
    pyglet.app.run()