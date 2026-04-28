import os
import sys
from collections import deque

import numpy as np
import pygame

try:
    from moviepy.editor import AudioFileClip, ImageSequenceClip, afx  
except ModuleNotFoundError:
    try:
        from moviepy import AudioFileClip, ImageSequenceClip, afx  
    except ModuleNotFoundError:
        AudioFileClip = None
        ImageSequenceClip = None
        afx = None


def setup_console_encoding():
    """在 Windows 终端中启用 UTF-8，避免中文输入提示乱码。"""
    if os.name == "nt":
        os.system("chcp 65001 > nul")

    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def get_chinese_font(size):
    """获取支持中文显示的字体，避免 pygame 窗口中文字变成方块或乱码。"""
    font_names = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "NSimSun",
        "Arial Unicode MS",
    ]

    for font_name in font_names:
        font_path = pygame.font.match_font(font_name)
        if font_path:
            return pygame.font.Font(font_path, size)

    windows_font_paths = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    for font_path in windows_font_paths:
        if os.path.exists(font_path):
            return pygame.font.Font(font_path, size)

    print("警告: 未找到中文字体，窗口中的中文可能无法正常显示。")
    return pygame.font.Font(None, size)


setup_console_encoding()

class RiverCrossingGame:
    def __init__(self, missionaries=3, cannibals=3, boat_capacity=2):
        # 游戏参数
        self.missionaries = missionaries
        self.cannibals = cannibals
        self.boat_capacity = boat_capacity
        
        # 状态初始化
        self.state = (missionaries, cannibals, 1)  # (左岸传教士, 左岸野人, 船的位置: 1=左岸, 0=右岸)
        self.solution_path = []
        self.current_step = 0
        self.auto_play = False
        self.speed = 1.0
        self.animation_progress = 1.0
        self.animation_duration = 1.8
        self.is_animating = False
        self.animation_from_step = 0
        self.animation_to_step = 0
        self.recording_video = False
        self.video_fps = 30
        self.video_capture_interval = 1.0 / self.video_fps
        self.video_capture_timer = 0.0
        
        # Pygame初始化
        pygame.init()
        try:
            pygame.mixer.init()
            self.audio_available = True
        except pygame.error as e:
            self.audio_available = False
            print(f"音频模块初始化失败，背景音乐不可用: {e}")

        self.music_path = None
        self.music_loaded = False
        self.music_playing = False
        self.music_volume = 0.45
        self.width = 1000
        self.height = 600
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption(f"野人过河问题 ({missionaries}传教士, {cannibals}野人)")
        
        # 颜色定义
        self.COLORS = {
            'river': (135, 206, 235),  # 天蓝色河流
            'boat': (101, 67, 33),     # 棕色船
            'text': (0, 0, 0),
            'button': (70, 130, 180),  # 钢蓝色按钮
            'button_hover': (100, 149, 237),  # 浅蓝色悬停
            'sky': (214, 238, 255),
            'grass': (79, 166, 93),
            'dark_grass': (47, 124, 68),
            'wave': (66, 150, 220),
            'shore': (235, 203, 137),
        }
        
        # 位置参数
        self.bank_width = 150
        self.river_width = self.width - 2 * self.bank_width
        self.left_bank_rect = pygame.Rect(0, 0, self.bank_width, self.height)
        self.river_rect = pygame.Rect(self.bank_width, 0, self.river_width, self.height)
        self.right_bank_rect = pygame.Rect(self.width - self.bank_width, 0, self.bank_width, self.height)
        self.boat_y = 405
        self.boat_width = 150
        self.boat_height = 50
        self.left_boat_x = self.bank_width - 45
        self.right_boat_x = self.width - self.bank_width - self.boat_width + 45
        
        # 按钮定义
        self.buttons = {
            'prev': pygame.Rect(20, 20, 100, 40),
            'next': pygame.Rect(140, 20, 100, 40),
            'auto': pygame.Rect(260, 20, 120, 40),
            'solve': pygame.Rect(400, 20, 120, 40),
            'video': pygame.Rect(540, 20, 120, 40)
        }
        
        # 字体：使用支持中文的字体，避免 pygame 默认字体显示中文乱码
        self.font = get_chinese_font(24)
        self.big_font = get_chinese_font(32)

        # 资源文件：把图片和音乐放到 characters 文件夹里即可自动加载
        self.character_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "characters")
        self.character_images = self.load_character_images()
        self.load_background_music()
        
        # 求解路径
        self.solution_path = self.solve_problem()
        
        # 截图帧（用于生成视频）
        self.capture_frames = []
        
    def is_valid_state(self, state):
        """检查状态是否合法"""
        m_left, c_left, boat = state
        m_right = self.missionaries - m_left
        c_right = self.cannibals - c_left
        
        # 传教士不能少于野人（除非没有传教士）
        if m_left > 0 and c_left > m_left:
            return False
        if m_right > 0 and c_right > m_right:
            return False
        
        # 人数不能为负数
        if m_left < 0 or c_left < 0 or m_right < 0 or c_right < 0:
            return False
            
        return True
    
    def get_possible_moves(self, state):
        """获取所有可能的移动"""
        m_left, c_left, boat = state
        moves = []
        
        if boat == 1:  # 船在左岸
            for m in range(self.missionaries + 1):
                for c in range(self.cannibals + 1):
                    if 1 <= m + c <= self.boat_capacity and m <= m_left and c <= c_left:
                        new_state = (m_left - m, c_left - c, 0)
                        if self.is_valid_state(new_state):
                            moves.append((m, c, new_state))
        else:  # 船在右岸
            m_right = self.missionaries - m_left
            c_right = self.cannibals - c_left
            for m in range(self.missionaries + 1):
                for c in range(self.cannibals + 1):
                    if 1 <= m + c <= self.boat_capacity and m <= m_right and c <= c_right:
                        new_state = (m_left + m, c_left + c, 1)
                        if self.is_valid_state(new_state):
                            moves.append((m, c, new_state))
        return moves
    
    def solve_problem(self):
        
        start_state = (self.missionaries, self.cannibals, 1)
        goal_state = (0, 0, 0)
        
        queue = deque([([start_state], [])])
        visited = set([start_state])
        
        while queue:
            path, moves = queue.popleft()
            current_state = path[-1]
            
            if current_state == goal_state:
                return list(zip(path, [None] + moves))
            
            for move in self.get_possible_moves(current_state):
                m_move, c_move, new_state = move
                if new_state not in visited:
                    visited.add(new_state)
                    new_path = path + [new_state]
                    new_moves = moves + [(m_move, c_move)]
                    queue.append((new_path, new_moves))
        
        return []
    
    def ease_in_out(self, t):
        """平滑缓动，让船移动更接近演示视频的连续动画效果。"""
        return t * t * (3 - 2 * t)

    def get_boat_x_for_state(self, state):
        """根据状态返回船的停靠位置。"""
        return self.left_boat_x if state[2] == 1 else self.right_boat_x

    def get_moving_passengers(self, from_state, to_state):
        """根据前后状态计算正在船上的具体角色编号。"""
        m_from, c_from, _ = from_state
        m_to, c_to, boat_to = to_state
        passengers = []

        if boat_to == 0:  # 左岸到右岸：搬走左岸末尾的角色
            passengers.extend(('C', index) for index in range(c_to, c_from))
            passengers.extend(('M', index) for index in range(m_to, m_from))
        else:  # 右岸到左岸：搬走右岸开头的角色
            passengers.extend(('C', index) for index in range(c_from, c_to))
            passengers.extend(('M', index) for index in range(m_from, m_to))

        return passengers

    def get_bank_character_indices(self, state):
        """根据状态返回左右两岸当前拥有的具体角色编号。"""
        m_left, c_left, _ = state
        return {
            'left': {
                'M': list(range(m_left)),
                'C': list(range(c_left)),
            },
            'right': {
                'M': list(range(m_left, self.missionaries)),
                'C': list(range(c_left, self.cannibals)),
            },
        }

    def get_display_context(self):
        """返回当前绘制所需两岸角色、船位置和船上乘客。"""
        if not self.is_animating or not self.solution_path:
            return self.get_bank_character_indices(self.state), self.get_boat_x_for_state(self.state), None

        from_state = self.solution_path[self.animation_from_step][0]
        to_state = self.solution_path[self.animation_to_step][0]
        progress = self.ease_in_out(self.animation_progress)
        start_x = self.get_boat_x_for_state(from_state)
        end_x = self.get_boat_x_for_state(to_state)
        boat_x = start_x + (end_x - start_x) * progress
        passengers = self.get_moving_passengers(from_state, to_state)
        bank_indices = self.get_bank_character_indices(from_state)

        # 动画过程中，船上的角色既不在出发岸，也不提前出现在目标岸。
        source_side = 'left' if from_state[2] == 1 else 'right'
        for kind, character_index in passengers:
            if character_index in bank_indices[source_side][kind]:
                bank_indices[source_side][kind].remove(character_index)

        return bank_indices, boat_x, passengers

    def start_step_animation(self, target_step, keep_auto=False):
        """启动从当前步骤到目标步骤的过河动画。"""
        if not self.solution_path or target_step == self.current_step:
            return
        if target_step < 0 or target_step >= len(self.solution_path):
            return

        self.animation_from_step = self.current_step
        self.animation_to_step = target_step
        self.animation_progress = 0.0
        self.is_animating = True
        self.play_background_music()
        if not keep_auto:
            self.auto_play = False

    def set_auto_play(self, enabled, record_video=False):
        """切换自动演示状态，并同步控制背景音乐和视频录制。"""
        self.auto_play = enabled
        self.recording_video = enabled and record_video
        if enabled:
            if record_video:
                self.capture_frames = []
                self.video_capture_timer = 0.0
                print(f"开始录制视频帧，录制帧率: {self.video_fps} FPS")
            if self.solution_path and self.current_step < len(self.solution_path) - 1:
                self.play_background_music()
        elif not self.is_animating:
            self.stop_background_music()
            self.recording_video = False

    def reset_demo(self):
        """重置演示状态并停止音乐。"""
        self.current_step = 0
        self.state = self.solution_path[0][0] if self.solution_path else (self.missionaries, self.cannibals, 1)
        self.auto_play = False
        self.is_animating = False
        self.recording_video = False
        self.animation_progress = 1.0
        self.stop_background_music()

    def finish_animation(self):
        """完成当前动画并切换到目标状态。"""
        self.current_step = self.animation_to_step
        self.state = self.solution_path[self.current_step][0]
        self.animation_progress = 1.0
        self.is_animating = False
        if self.current_step >= len(self.solution_path) - 1:
            self.auto_play = False
            self.recording_video = False
        if not self.auto_play or self.current_step >= len(self.solution_path) - 1:
            self.stop_background_music()

    def update_animation(self, dt):
        """更新船的连续移动动画。"""
        if not self.is_animating:
            return
        self.animation_progress += dt / self.animation_duration
        if self.animation_progress >= 1.0:
            self.finish_animation()

    def load_character_images(self):
        """从 characters 文件夹加载角色图片。"""
        images = {'M': [], 'C': []}
        supported_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')

        if not os.path.isdir(self.character_dir):
            os.makedirs(self.character_dir, exist_ok=True)
            print(f"已创建角色图片文件夹: {self.character_dir}")
            print("把传教士图片命名为 missionary_1.png，野人图片命名为 cannibal_1.png 后重新运行程序。")
            return images

        for filename in sorted(os.listdir(self.character_dir)):
            lower_name = filename.lower()
            if not lower_name.endswith(supported_exts):
                continue

            if lower_name.startswith(('missionary', 'm_', 'm-', 'm.')):
                kind = 'M'
            elif lower_name.startswith(('cannibal', 'c_', 'c-', 'c.')):
                kind = 'C'
            else:
                continue

            image_path = os.path.join(self.character_dir, filename)
            try:
                image = pygame.image.load(image_path).convert_alpha()
                images[kind].append(image)
            except pygame.error as e:
                print(f"角色图片加载失败: {image_path}，原因: {e}")

        print(f"已加载角色图片: 传教士 {len(images['M'])} 张，野人 {len(images['C'])} 张")
        return images

    def load_background_music(self):
        """从 characters 文件夹加载第一首 MP3 背景音乐。"""
        if not self.audio_available:
            return
        if not os.path.isdir(self.character_dir):
            return

        mp3_files = sorted(
            filename for filename in os.listdir(self.character_dir)
            if filename.lower().endswith(".mp3")
        )
        if not mp3_files:
            print("未在 characters 文件夹中找到 MP3 音乐文件。")
            return

        self.music_path = os.path.join(self.character_dir, mp3_files[0])
        try:
            pygame.mixer.music.load(self.music_path)
            pygame.mixer.music.set_volume(self.music_volume)
            self.music_loaded = True
            print(f"已加载背景音乐: {self.music_path}")
        except pygame.error as e:
            self.music_loaded = False
            print(f"背景音乐加载失败: {self.music_path}，原因: {e}")

    def play_background_music(self):
        """开始播放背景音乐，已播放时不重复启动。"""
        if not self.music_loaded or self.music_playing:
            return
        try:
            pygame.mixer.music.play(-1)
            self.music_playing = True
        except pygame.error as e:
            print(f"背景音乐播放失败: {e}")

    def create_video_audio_clip(self, duration):
        """为导出视频创建与画面等长的背景音乐片段。"""
        audio_clip = None
        try:
            audio_clip = AudioFileClip(self.music_path)
            if audio_clip.duration < duration and afx is not None:
                audio_clip = audio_clip.fx(afx.audio_loop, duration=duration)
            return audio_clip.subclip(0, duration)
        except Exception as e:
            print(f"添加背景音乐失败，将生成无声视频。原因: {e}")
            if audio_clip is not None:
                audio_clip.close()
            return None

    def stop_background_music(self):
        """停止背景音乐。"""
        if not self.music_loaded or not self.music_playing:
            return
        pygame.mixer.music.stop()
        self.music_playing = False

    def get_character_image(self, kind, index):
        """按角色类型和序号循环获取图片。"""
        images = self.character_images.get(kind, [])
        if not images:
            return None
        return images[index % len(images)]

    def draw_character_image(self, image, x, y, scale=1.0):
        """绘制角色图片，底部居中到指定坐标。"""
        target_height = max(24, int(72 * scale))
        ratio = image.get_width() / image.get_height()
        target_width = max(18, int(target_height * ratio))
        scaled_image = pygame.transform.smoothscale(image, (target_width, target_height))
        image_rect = scaled_image.get_rect(midbottom=(int(x), int(y)))
        self.screen.blit(scaled_image, image_rect)

    def draw_character(self, x, y, kind, scale=1.0, index=0):
        """优先绘制本地动漫角色图片；没有图片时绘制默认卡通小人。"""
        image = self.get_character_image(kind, index)
        if image:
            self.draw_character_image(image, x, y + 58 * scale, scale)
            return

        head_radius = int(14 * scale)
        body_w = int(24 * scale)
        body_h = int(34 * scale)
        leg_h = int(16 * scale)
        skin = (255, 224, 189)

        if kind == 'C':
            body_color = (206, 49, 49)
            label_color = (255, 255, 255)
            hair_color = (45, 28, 22)
        else:
            body_color = (42, 104, 205)
            label_color = (0, 0, 0)
            hair_color = (245, 245, 245)

        pygame.draw.circle(self.screen, skin, (int(x), int(y)), head_radius)
        pygame.draw.circle(self.screen, hair_color, (int(x), int(y - 4 * scale)), head_radius, max(1, int(3 * scale)))
        pygame.draw.circle(self.screen, (0, 0, 0), (int(x - 5 * scale), int(y - 2 * scale)), max(1, int(2 * scale)))
        pygame.draw.circle(self.screen, (0, 0, 0), (int(x + 5 * scale), int(y - 2 * scale)), max(1, int(2 * scale)))
        pygame.draw.arc(self.screen, (90, 40, 30), (int(x - 7 * scale), int(y), int(14 * scale), int(9 * scale)), 0, 3.14, max(1, int(2 * scale)))

        body_rect = pygame.Rect(int(x - body_w / 2), int(y + head_radius - 1), body_w, body_h)
        pygame.draw.rect(self.screen, body_color, body_rect, border_radius=max(4, int(6 * scale)))
        pygame.draw.line(self.screen, (50, 40, 35), (int(x - body_w / 2), int(y + head_radius + body_h)), (int(x - 8 * scale), int(y + head_radius + body_h + leg_h)), max(2, int(3 * scale)))
        pygame.draw.line(self.screen, (50, 40, 35), (int(x + body_w / 2), int(y + head_radius + body_h)), (int(x + 8 * scale), int(y + head_radius + body_h + leg_h)), max(2, int(3 * scale)))

        label = self.font.render(kind, True, label_color)
        label_rect = label.get_rect(center=body_rect.center)
        self.screen.blit(label, label_rect)

    def draw_bank(self, rect, side, bank_indices=None):
        """绘制河岸和岸上的小人。"""
        if bank_indices is None:
            bank_indices = self.get_bank_character_indices(self.state)

        pygame.draw.rect(self.screen, self.COLORS['grass'], rect)
        pygame.draw.rect(self.screen, self.COLORS['shore'], (rect.left, self.boat_y - 25, rect.width, 95))
        pygame.draw.line(self.screen, self.COLORS['dark_grass'], (rect.left, self.boat_y - 25), (rect.right, self.boat_y - 25), 4)

        c_indices = bank_indices[side]['C']
        m_indices = bank_indices[side]['M']

        for draw_i, character_index in enumerate(c_indices):
            x_offset = 35 + (draw_i % 3) * 38
            y_offset = 115 + (draw_i // 3) * 72
            x = rect.left + (x_offset if side == 'left' else rect.width - x_offset)
            y = rect.top + y_offset
            self.draw_character(x, y, 'C', 0.85, character_index)

        for draw_i, character_index in enumerate(m_indices):
            x_offset = 35 + (draw_i % 3) * 38
            y_offset = 310 + (draw_i // 3) * 72
            x = rect.left + (x_offset if side == 'left' else rect.width - x_offset)
            y = rect.top + y_offset
            self.draw_character(x, y, 'M', 0.85, character_index)

        title = "左岸" if side == 'left' else "右岸"
        count_text = f"{title}  野人:{len(c_indices)}  传教士:{len(m_indices)}"
        text_surf = self.font.render(count_text, True, self.COLORS['text'])
        self.screen.blit(text_surf, (rect.left + 12, rect.top + 20))
    
    def draw_river(self):
        """绘制动态河流。"""
        pygame.draw.rect(self.screen, self.COLORS['river'], self.river_rect)
        time_offset = pygame.time.get_ticks() / 450
        for row, wave_y in enumerate(range(145, 455, 45)):
            for i in range(8):
                wave_x = self.bank_width + i * 110 + int((time_offset * (row + 1) * 7) % 70)
                pygame.draw.arc(self.screen, self.COLORS['wave'], (wave_x, wave_y, 70, 22), 0, 3.14, 3)

    def draw_boat_shape(self, boat_x, boat_y):
        """绘制更接近演示效果的木船。"""
        hull = [
            (int(boat_x), int(boat_y)),
            (int(boat_x + self.boat_width), int(boat_y)),
            (int(boat_x + self.boat_width - 24), int(boat_y + self.boat_height)),
            (int(boat_x + 24), int(boat_y + self.boat_height)),
        ]
        pygame.draw.polygon(self.screen, self.COLORS['boat'], hull)
        pygame.draw.polygon(self.screen, (54, 35, 20), hull, 3)
        pygame.draw.line(self.screen, (54, 35, 20), (int(boat_x + 20), int(boat_y + 13)), (int(boat_x + self.boat_width - 20), int(boat_y + 13)), 3)

    def draw_boat(self, boat_x=None, passengers=None):
        """绘制船和船上的人。"""
        if boat_x is None:
            boat_x = self.get_boat_x_for_state(self.state)

        boat_y = self.boat_y
        self.draw_boat_shape(boat_x, boat_y)

        if passengers:
            total_width = max(1, len(passengers) - 1) * 42
            start_x = boat_x + self.boat_width / 2 - total_width / 2
            for i, (kind, character_index) in enumerate(passengers):
                self.draw_character(start_x + i * 42, boat_y - 42, kind, 0.72, character_index)

        pos_text = "左岸" if boat_x < self.width / 2 else "右岸"
        text = self.font.render(f"船在{pos_text}", True, self.COLORS['text'])
        self.screen.blit(text, (int(boat_x + 30), boat_y + self.boat_height + 8))
    
    def draw_buttons(self):
        """绘制控制按钮"""
        mouse_pos = pygame.mouse.get_pos()
        
        for button_name, button_rect in self.buttons.items():
            # 检查鼠标悬停
            is_hover = button_rect.collidepoint(mouse_pos)
            color = self.COLORS['button_hover'] if is_hover else self.COLORS['button']
            
            pygame.draw.rect(self.screen, color, button_rect, border_radius=5)
            pygame.draw.rect(self.screen, (0, 0, 0), button_rect, 2, border_radius=5)
            
            # 按钮文字
            text_map = {
                'prev': "上一步",
                'next': "下一步",
                'auto': "自动播放",
                'solve': "重新求解",
                'video': "生成视频"
            }
            
            text = self.font.render(text_map[button_name], True, (255, 255, 255))
            text_rect = text.get_rect(center=button_rect.center)
            self.screen.blit(text, text_rect)
    
    def draw_info(self):
        """绘制状态信息"""
        # 显示当前步骤
        if self.solution_path:
            step_text = f"步骤: {self.current_step}/{len(self.solution_path)-1}"
            text = self.big_font.render(step_text, True, self.COLORS['text'])
            self.screen.blit(text, (self.width - 200, 20))
            
            # 显示当前状态
            state_text = f"状态: ({self.state[0]}M, {self.state[1]}C, 船在{'左岸' if self.state[2] == 1 else '右岸'})"
            text = self.font.render(state_text, True, self.COLORS['text'])
            self.screen.blit(text, (self.width - 300, 60))
            
            # 显示解决方案步骤
            if self.current_step < len(self.solution_path):
                if self.current_step > 0:
                    _, move = self.solution_path[self.current_step-1]
                    if move:
                        m_move, c_move = move
                        action_text = f"上一步动作: 移动{m_move}传教士, {c_move}野人到{'右岸' if self.state[2] == 0 else '左岸'}"
                        text = self.font.render(action_text, True, (0, 100, 0))
                        self.screen.blit(text, (20, 80))
        
        # 显示问题描述
        desc = f"野人过河问题: {self.missionaries}传教士, {self.cannibals}野人, 船容量: {self.boat_capacity}"
        text = self.font.render(desc, True, (0, 0, 150))
        self.screen.blit(text, (20, self.height - 40))
    
    def capture_frame(self):
        """捕获当前帧用于生成视频"""
        frame_data = pygame.surfarray.array3d(self.screen)
        frame_data = np.transpose(frame_data, (1, 0, 2))
        self.capture_frames.append(frame_data)

    def update_video_capture(self, dt):
        """按固定帧率录制视频，避免 60FPS 全量录制后低帧率导出导致视频变慢。"""
        if not self.recording_video:
            return

        self.video_capture_timer += dt
        while self.video_capture_timer >= self.video_capture_interval:
            self.capture_frame()
            self.video_capture_timer -= self.video_capture_interval
    
    def generate_video(self, filename="river_crossing.mp4", fps=None):
        """生成演示视频"""
        if fps is None:
            fps = self.video_fps

        if ImageSequenceClip is None:
            print("未安装 MoviePy，无法生成视频。请运行: pip install moviepy")
            return

        if not self.capture_frames:
            print("没有捕获到帧！请先点击“自动播放”录制演示过程，再点击“生成视频”。")
            return
        
        estimated_seconds = len(self.capture_frames) / fps
        print(f"正在生成视频，共{len(self.capture_frames)}帧，导出帧率 {fps} FPS，预计时长 {estimated_seconds:.1f} 秒...")
        
        clip = None
        audio_clip = None
        try:
            clip = ImageSequenceClip(self.capture_frames, fps=fps)

            if self.music_path and os.path.exists(self.music_path) and AudioFileClip is not None:
                audio_clip = self.create_video_audio_clip(estimated_seconds)
                if audio_clip is not None:
                    clip = clip.set_audio(audio_clip)
                    print(f"已为视频添加背景音乐: {self.music_path}")
            else:
                print("未找到可用背景音乐，将生成无声视频。")

            clip.write_videofile(filename, codec='libx264', audio_codec='aac', fps=fps)
            print(f"视频已生成: {filename}")
            print(f"视频时长约: {estimated_seconds:.1f} 秒")
            
        except Exception as e:
            print(f"生成视频时出错: {e}")
        finally:
            if audio_clip is not None:
                audio_clip.close()
            if clip is not None:
                clip.close()
    
    def draw(self):
        """绘制整个界面"""
        # 清屏
        self.screen.fill(self.COLORS['sky'])
        bank_indices, boat_x, boat_passengers = self.get_display_context()
        
        # 绘制各个组件
        self.draw_river()
        self.draw_bank(self.left_bank_rect, 'left', bank_indices)
        self.draw_bank(self.right_bank_rect, 'right', bank_indices)
        self.draw_boat(boat_x, boat_passengers)
        self.draw_buttons()
        self.draw_info()
        
        # 更新显示
        pygame.display.flip()
        
    
    def handle_events(self):
        """处理事件"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.stop_background_music()
                pygame.quit()
                sys.exit()
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = pygame.mouse.get_pos()
                
                # 检查按钮点击
                if self.buttons['prev'].collidepoint(mouse_pos) and self.current_step > 0 and not self.is_animating:
                    self.start_step_animation(self.current_step - 1)
                
                elif self.buttons['next'].collidepoint(mouse_pos) and self.current_step < len(self.solution_path) - 1 and not self.is_animating:
                    self.start_step_animation(self.current_step + 1)
                
                elif self.buttons['auto'].collidepoint(mouse_pos):
                    self.set_auto_play(not self.auto_play, record_video=not self.auto_play)
                
                elif self.buttons['solve'].collidepoint(mouse_pos):
                    # 重新求解
                    self.solution_path = self.solve_problem()
                    self.reset_demo()
                
                elif self.buttons['video'].collidepoint(mouse_pos):
                    # 生成视频
                    self.generate_video()
            
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT and self.current_step > 0 and not self.is_animating:
                    self.start_step_animation(self.current_step - 1)
                elif event.key == pygame.K_RIGHT and self.current_step < len(self.solution_path) - 1 and not self.is_animating:
                    self.start_step_animation(self.current_step + 1)
                elif event.key == pygame.K_SPACE:
                    self.set_auto_play(not self.auto_play, record_video=not self.auto_play)
                elif event.key == pygame.K_r:  # 重置
                    self.reset_demo()
    
    def run(self):
        """运行主循环"""
        clock = pygame.time.Clock()
        auto_timer = 0
        
        print("=== 野人过河问题求解器 ===")
        print(f"问题: {self.missionaries}传教士, {self.cannibals}野人, 船容量: {self.boat_capacity}")
        print(f"找到解决方案: {len(self.solution_path)-1} 步")
        
        if not self.solution_path:
            print("警告: 未找到解决方案！")
        else:
            print("解决方案步骤:")
            for i, (state, move) in enumerate(self.solution_path):
                if i > 0:
                    print(f"步骤{i}: 移动{move[0]}传教士, {move[1]}野人到{'右岸' if state[2] == 0 else '左岸'} -> {state}")
        
        while True:
            self.handle_events()
            
            dt = clock.get_time() / 1000
            self.update_animation(dt)
            
            # 自动播放
            if self.auto_play and not self.is_animating:
                if self.current_step < len(self.solution_path) - 1:
                    auto_timer += dt
                    if auto_timer >= 0.35 / self.speed:
                        self.start_step_animation(self.current_step + 1, keep_auto=True)
                        auto_timer = 0
                else:
                    self.set_auto_play(False)
            
            self.draw()
            self.update_video_capture(dt)
            clock.tick(60)  # 60 FPS

# 用户输入界面
def get_user_input():
    """获取用户输入"""
    print("=== 野人过河问题配置 ===")
    
    while True:
        try:
            missionaries = int(input("请输入传教士数量 (默认3): ") or "3")
            cannibals = int(input("请输入野人数量 (默认3): ") or "3")
            boat_capacity = int(input("请输入船的最大容量 (默认2): ") or "2")
            
            if missionaries <= 0 or cannibals <= 0 or boat_capacity <= 0:
                print("请输入正整数！")
                continue
            
            if missionaries > 10 or cannibals > 10:
                print("数量过大可能导致性能问题，建议不超过10")
                continue
                
            return missionaries, cannibals, boat_capacity
            
        except ValueError:
            print("请输入有效的数字！")

# 主程序
if __name__ == "__main__":
    # 获取用户输入
    missionaries, cannibals, boat_capacity = get_user_input()
    
    # 创建并运行游戏
    game = RiverCrossingGame(missionaries, cannibals, boat_capacity)
    game.run()
