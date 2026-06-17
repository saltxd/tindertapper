"""TinderTapper - Auto-liker for Tinder via iPhone Mirroring."""

import os
import sys
import platform
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import random
from datetime import datetime

# Make sure this script's own directory is importable (for `mirror`) even when
# launched from another working directory.
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)


def get_resource_path(filename):
    """Get path to resource file, works for both dev and bundled app."""
    paths_to_check = []

    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            paths_to_check.append(os.path.join(sys._MEIPASS, 'resources', filename))
        exe_dir = os.path.dirname(sys.executable)
        paths_to_check.append(os.path.join(exe_dir, 'resources', filename))
        if '.app' in exe_dir:
            app_contents = os.path.dirname(exe_dir)
            paths_to_check.append(os.path.join(app_contents, 'Resources', 'resources', filename))

    paths_to_check.append(os.path.join(_script_dir, 'resources', filename))

    for path in paths_to_check:
        if os.path.exists(path):
            return path

    return os.path.join(_script_dir, 'resources', filename)


class DebugLogger:
    """Handles debug logging with timestamped screenshots and log files."""

    def __init__(self, enabled=False):
        self.enabled = enabled
        self.session_dir = None
        self.log_file = None
        self.step_count = 0
        self.attempt_count = 0

    def start_session(self):
        if not self.enabled:
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = f"/tmp/tinder_debug/session_{timestamp}"
        os.makedirs(self.session_dir, exist_ok=True)
        self.log_file = open(f"{self.session_dir}/debug.log", "w")
        self.step_count = 0
        self.attempt_count = 0
        self.log(f"Debug session started: {timestamp}")
        self.log(f"Session directory: {self.session_dir}")

    def end_session(self):
        if self.log_file:
            self.log("Session ended")
            self.log_file.close()
            self.log_file = None

    def new_attempt(self):
        self.attempt_count += 1
        self.step_count = 0
        self.log(f"\n{'='*50}")
        self.log(f"ATTEMPT {self.attempt_count}")
        self.log(f"{'='*50}")

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {message}"
        print(line)
        if self.log_file:
            self.log_file.write(line + "\n")
            self.log_file.flush()

    def save_screenshot(self, image, step_name):
        if not self.enabled or not self.session_dir or image is None:
            return None
        self.step_count += 1
        filename = f"attempt{self.attempt_count:03d}_step{self.step_count:02d}_{step_name}.png"
        filepath = os.path.join(self.session_dir, filename)
        try:
            image.save(filepath)
            self.log(f"Screenshot saved: {filename}")
            return filepath
        except Exception as e:
            self.log(f"Failed to save screenshot: {e}")
            return None

    def log_match_result(self, template_name, result, threshold, best_match=None):
        if result:
            x, y, confidence = result
            status = "FOUND" if confidence >= threshold else "BELOW_THRESHOLD"
            self.log(f"  {template_name}: {status} at ({x}, {y}) "
                     f"confidence={confidence:.3f} threshold={threshold}")
        elif best_match:
            x, y, confidence = best_match
            self.log(f"  {template_name}: NOT_FOUND (best={confidence:.3f}, "
                     f"threshold={threshold}, at ({x}, {y}))")
        else:
            self.log(f"  {template_name}: NOT_FOUND (threshold={threshold})")


debug_logger = DebugLogger(enabled=False)


class TinderTapperApp:
    """Tkinter GUI for Tinder auto-liker."""

    SPEED_DELAYS = {
        'fast': (1.5, 3.0),
        'normal': (3.0, 5.0),
        'slow': (5.0, 9.0),
    }

    THRESHOLDS = {
        'like': 0.65,
        'match_dismiss': 0.60,
        'out_of_likes': 0.55,
        'no_profiles': 0.55,
    }

    MAX_CONSECUTIVE_FAILURES = 5
    RANDOM_OFFSET_RANGE = 20  # +-20px in image coords (+-10px on screen)
    LONG_PAUSE_INTERVAL = (8, 15)  # Every 8-15 likes, take a long pause
    LONG_PAUSE_DURATION = (8, 20)  # Long pause: 8-20 seconds

    def __init__(self, root):
        self.root = root
        self.root.title("TinderTapper")
        self.root.geometry("400x580")
        self.root.resizable(False, False)
        self.running = False
        self.build_ui()

    def build_ui(self):
        # Header
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill='x', pady=(20, 5))

        ttk.Label(
            header_frame,
            text="TinderTapper",
            font=('Helvetica', 24, 'bold')
        ).pack()

        ttk.Label(
            header_frame,
            text="Auto-liker for Tinder",
            font=('Helvetica', 10),
            foreground='gray'
        ).pack()

        # Options section
        ttk.Separator(self.root).pack(fill='x', padx=20, pady=15)

        self.auto_dismiss_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self.root,
            text="Auto-dismiss matches (keep swiping)",
            variable=self.auto_dismiss_var
        ).pack(anchor='w', padx=20, pady=(0, 0))

        self.debug_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.root,
            text="Debug mode (save screenshots to /tmp/tinder_debug/)",
            variable=self.debug_mode_var
        ).pack(anchor='w', padx=20, pady=(0, 5))

        # Speed section
        ttk.Separator(self.root).pack(fill='x', padx=20, pady=10)

        ttk.Label(
            self.root,
            text="Speed:",
            font=('Helvetica', 11, 'bold')
        ).pack(anchor='w', padx=20)

        self.speed_var = tk.StringVar(value="normal")
        speeds = [
            ("Fast (1.5-3 sec between likes)", "fast"),
            ("Normal (3-5 sec)", "normal"),
            ("Slow (5-9 sec)", "slow"),
        ]
        for text, value in speeds:
            ttk.Radiobutton(
                self.root, text=text,
                variable=self.speed_var, value=value
            ).pack(anchor='w', padx=40)

        # Stop after section
        ttk.Separator(self.root).pack(fill='x', padx=20, pady=15)

        ttk.Label(
            self.root,
            text="Stop after:",
            font=('Helvetica', 11, 'bold')
        ).pack(anchor='w', padx=20)

        self.stop_var = tk.StringVar(value="100")

        for text, value in [("10 likes", "10"), ("25 likes", "25"),
                            ("50 likes", "50"), ("100 likes (daily limit)", "100")]:
            ttk.Radiobutton(
                self.root, text=text,
                variable=self.stop_var, value=value
            ).pack(anchor='w', padx=40)

        custom_frame = ttk.Frame(self.root)
        custom_frame.pack(anchor='w', padx=40, pady=2)
        ttk.Radiobutton(
            custom_frame, text="Custom:",
            variable=self.stop_var, value="custom"
        ).pack(side='left')
        self.custom_count = ttk.Entry(custom_frame, width=6)
        self.custom_count.pack(side='left', padx=5)
        self.custom_count.insert(0, "200")

        ttk.Radiobutton(
            self.root, text="Until I stop",
            variable=self.stop_var, value="unlimited"
        ).pack(anchor='w', padx=40)

        # Buttons
        ttk.Separator(self.root).pack(fill='x', padx=20, pady=15)

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=10)

        self.start_btn = ttk.Button(
            btn_frame, text="START",
            command=self.start, width=15
        )
        self.start_btn.grid(row=0, column=0, padx=10)

        self.stop_btn = ttk.Button(
            btn_frame, text="STOP",
            command=self.stop, width=15,
            state='disabled'
        )
        self.stop_btn.grid(row=0, column=1, padx=10)

        # Status section
        ttk.Separator(self.root).pack(fill='x', padx=20, pady=10)

        status_frame = ttk.Frame(self.root)
        status_frame.pack(pady=5)

        self.count_var = tk.StringVar(value="0")
        ttk.Label(
            status_frame,
            textvariable=self.count_var,
            font=('Helvetica', 32, 'bold')
        ).pack()

        self.match_count_var = tk.StringVar(value="")
        ttk.Label(
            status_frame,
            textvariable=self.match_count_var,
            font=('Helvetica', 12),
            foreground='#e74c3c'
        ).pack()

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            font=('Helvetica', 10),
            foreground='gray'
        ).pack(pady=(3, 15))

    def get_delay_range(self):
        return self.SPEED_DELAYS.get(self.speed_var.get(), (3.0, 5.0))

    def get_max_likes(self):
        stop = self.stop_var.get()
        if stop == 'unlimited':
            return -1
        if stop == 'custom':
            try:
                return int(self.custom_count.get())
            except ValueError:
                return 100
        return int(stop)

    def start(self):
        try:
            from mirror import find_iphone_window, capture_window
        except ImportError as e:
            messagebox.showerror("Error", f"Failed to import mirror module:\n{e}")
            self.root.lift()
            self.root.focus_force()
            return

        # Check for like template
        like_path = get_resource_path('tinder_like.png')
        if not os.path.exists(like_path):
            messagebox.showerror(
                "Missing Template",
                f"Like button template not found:\n{like_path}\n\n"
                "Capture a screenshot of Tinder and crop the green heart button.\n"
                "Save it as tinder_like.png in the resources folder."
            )
            self.root.lift()
            self.root.focus_force()
            return

        window = find_iphone_window()
        if not window:
            messagebox.showerror(
                "iPhone Not Found",
                "Can't find iPhone Mirroring window.\n\n"
                "Make sure:\n"
                "1. iPhone Mirroring is open\n"
                "2. Screen Recording permission is granted\n\n"
                "Go to System Settings > Privacy & Security > Screen Recording"
            )
            self.root.lift()
            self.root.focus_force()
            return

        try:
            test_capture = capture_window(window['id'])
            if test_capture is None:
                raise Exception("Capture returned None")
        except Exception:
            messagebox.showerror(
                "Permission Required",
                "Can't capture screen.\n\n"
                "Grant Screen Recording permission:\n"
                "System Settings > Privacy & Security > Screen Recording\n\n"
                "Then restart the app."
            )
            self.root.lift()
            self.root.focus_force()
            return

        self.running = True
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')

        thread = threading.Thread(target=self.run_liker, daemon=True)
        thread.start()

    def stop(self):
        self.running = False
        self.status_var.set("Stopping...")

    def update_status(self, message):
        self.root.after(0, lambda: self.status_var.set(message))

    def update_count(self, text):
        self.root.after(0, lambda: self.count_var.set(text))

    def update_matches(self, count):
        self.root.after(0, lambda: self.match_count_var.set(
            f"Matches: {count}" if count > 0 else ""
        ))

    def _should_stop(self):
        return not self.running

    def _dismiss_promo_popup(self, image, window, find_icon, click_at):
        """Check for and dismiss promotional popups (Double Date, etc). Returns True if dismissed."""
        # Try "Maybe later" button first
        ml_path = get_resource_path('tinder_maybe_later.png')
        if os.path.exists(ml_path):
            match = find_icon(image, 'tinder_maybe_later.png', threshold=0.60)
            if match:
                debug_logger.log(f"Promo popup detected! 'Maybe later' at ({match[0]}, {match[1]}) "
                               f"conf={match[2]:.3f}")
                click_at(match[0], match[1], window)
                time.sleep(1.0)
                return True

        # Try X dismiss button
        x_path = get_resource_path('tinder_dismiss_x.png')
        if os.path.exists(x_path):
            match = find_icon(image, 'tinder_dismiss_x.png', threshold=0.60)
            if match:
                debug_logger.log(f"Promo popup detected! X button at ({match[0]}, {match[1]}) "
                               f"conf={match[2]:.3f}")
                click_at(match[0], match[1], window)
                time.sleep(1.0)
                return True

        return False

    def _check_match_popup(self, image, window, find_icon, click_at, random_delay):
        """Check for and dismiss a match popup. Returns True if match was found."""
        if not self.auto_dismiss_var.get():
            return False

        dismiss_path = get_resource_path('tinder_match_dismiss.png')
        if not os.path.exists(dismiss_path):
            return False

        match_dismiss = find_icon(
            image, 'tinder_match_dismiss.png',
            threshold=self.THRESHOLDS['match_dismiss']
        )
        if match_dismiss:
            debug_logger.log(f"MATCH popup detected at ({match_dismiss[0]}, {match_dismiss[1]}) "
                           f"conf={match_dismiss[2]:.3f}")
            random_delay(0.8, 1.5, should_stop=self._should_stop)

            offset_x = random.randint(-15, 15)
            offset_y = random.randint(-8, 8)
            click_at(match_dismiss[0] + offset_x, match_dismiss[1] + offset_y, window)

            random_delay(0.5, 1.0, should_stop=self._should_stop)
            return True

        return False

    def run_liker(self):
        """Main automation loop. Runs in daemon thread."""
        global debug_logger

        from mirror import (
            find_iphone_window, capture_window, find_icon,
            click_at, random_delay
        )

        debug_logger.enabled = self.debug_mode_var.get()
        debug_logger.start_session()

        # Log resource paths
        debug_logger.log("TinderTapper Debug Info")
        debug_logger.log("=" * 50)
        for template in ['tinder_like.png', 'tinder_match_dismiss.png',
                         'tinder_maybe_later.png', 'tinder_dismiss_x.png',
                         'tinder_out_of_likes.png', 'tinder_no_profiles.png']:
            path = get_resource_path(template)
            exists = os.path.exists(path)
            debug_logger.log(f"  {template}: {path} -> {'EXISTS' if exists else 'MISSING'}")
        debug_logger.log("=" * 50)

        max_likes = self.get_max_likes()
        sent = 0
        matches_detected = 0
        consecutive_failures = 0
        capture_failures = 0
        next_long_pause = random.randint(*self.LONG_PAUSE_INTERVAL)

        while self.running:
            if max_likes > 0 and sent >= max_likes:
                break
            if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                self.update_status("Stopped: too many failures")
                break
            if capture_failures >= 2:
                self.update_status("Screen Recording permission needed")
                break

            count_text = f"{sent}" if max_likes < 0 else f"{sent} / {max_likes}"
            self.update_count(count_text)
            self.update_status("Looking...")

            try:
                debug_logger.new_attempt()
                debug_logger.log(f"Starting attempt (sent so far: {sent})")

                # Phase 1: Capture screen
                window = find_iphone_window()
                if not window:
                    debug_logger.log("iPhone Mirroring window not found!")
                    consecutive_failures += 1
                    self.update_status("Lost iPhone Mirroring window!")
                    time.sleep(1)
                    continue

                debug_logger.log(f"Window found: {window['owner']} (id={window['id']})")

                image = capture_window(window['id'])
                if image is None:
                    debug_logger.log("Capture failed!")
                    consecutive_failures += 1
                    capture_failures += 1
                    time.sleep(0.5)
                    continue

                debug_logger.log(f"Captured window: {image.size}")
                debug_logger.save_screenshot(image, "01_capture")

                # Phase 2: Check special states

                # 2a. Match popup?
                if self._check_match_popup(image, window, find_icon, click_at, random_delay):
                    matches_detected += 1
                    self.update_matches(matches_detected)
                    self.update_status("Match dismissed!")
                    debug_logger.log(f"Match dismissed! Total matches: {matches_detected}")
                    consecutive_failures = 0
                    continue

                # 2b. Out of likes?
                ool_path = get_resource_path('tinder_out_of_likes.png')
                if os.path.exists(ool_path):
                    out_of_likes = find_icon(
                        image, 'tinder_out_of_likes.png',
                        threshold=self.THRESHOLDS['out_of_likes']
                    )
                    if out_of_likes:
                        debug_logger.log("Out of likes detected!")
                        debug_logger.save_screenshot(image, "02_out_of_likes")
                        self.update_status(f"Out of likes! ({sent} sent)")
                        break

                # 2c. No more profiles?
                np_path = get_resource_path('tinder_no_profiles.png')
                if os.path.exists(np_path):
                    no_profiles = find_icon(
                        image, 'tinder_no_profiles.png',
                        threshold=self.THRESHOLDS['no_profiles']
                    )
                    if no_profiles:
                        debug_logger.log("No more profiles!")
                        debug_logger.save_screenshot(image, "02_no_profiles")
                        self.update_status(f"No more profiles! ({sent} sent)")
                        break

                # Phase 3: Find like button (bottom 30% of screen)
                img_height = image.size[1]
                min_like_y = int(img_height * 0.70)

                like_threshold = self.THRESHOLDS['like']
                like_pos = find_icon(
                    image, 'tinder_like.png',
                    threshold=like_threshold,
                    min_y=min_like_y
                )

                if like_pos:
                    debug_logger.log_match_result(
                        'tinder_like.png', like_pos, like_threshold
                    )
                else:
                    # Retry with fresh capture
                    debug_logger.log("Like button not found, retrying...")
                    time.sleep(0.5)
                    image = capture_window(window['id'])
                    if image:
                        like_pos = find_icon(
                            image, 'tinder_like.png',
                            threshold=like_threshold,
                            min_y=min_like_y
                        )
                        debug_logger.save_screenshot(image, "02_retry")

                    if like_pos:
                        debug_logger.log_match_result(
                            'tinder_like.png (retry)', like_pos, like_threshold
                        )
                    else:
                        best = find_icon(
                            image, 'tinder_like.png',
                            threshold=like_threshold,
                            min_y=min_like_y,
                            return_best_match=True
                        )
                        debug_logger.log_match_result(
                            'tinder_like.png', None, like_threshold, best_match=best
                        )

                if not like_pos:
                    # Check for promotional popups (Double Date, etc)
                    if self._dismiss_promo_popup(image, window, find_icon, click_at):
                        debug_logger.log("Promo popup dismissed, retrying...")
                        self.update_status("Dismissed popup")
                        consecutive_failures = 0
                        continue

                    debug_logger.log("FAIL: Like button not found after retry")
                    debug_logger.save_screenshot(image, "02_like_not_found")
                    self.update_status("No like button found")
                    consecutive_failures += 1
                    time.sleep(1)
                    continue

                # Phase 3b: Click with random offset
                offset_x = random.randint(-self.RANDOM_OFFSET_RANGE, self.RANDOM_OFFSET_RANGE)
                offset_y = random.randint(-self.RANDOM_OFFSET_RANGE, self.RANDOM_OFFSET_RANGE)

                click_x = like_pos[0] + offset_x
                click_y = like_pos[1] + offset_y

                debug_logger.log(f"Clicking like at ({click_x}, {click_y}) "
                               f"[base=({like_pos[0]}, {like_pos[1]}), offset=({offset_x}, {offset_y})]")
                click_at(click_x, click_y, window)
                self.update_status("Liked!")

                # Phase 4: Post-click
                sent += 1
                consecutive_failures = 0
                capture_failures = 0

                debug_logger.log(f"SUCCESS! Total sent: {sent}")

                # Brief pause for like animation
                random_delay(0.5, 1.0, should_stop=self._should_stop)
                if not self.running:
                    break

                # Check for match popup after like
                post_image = capture_window(window['id'])
                if post_image:
                    debug_logger.save_screenshot(post_image, "03_after_like")
                    if self._check_match_popup(post_image, window, find_icon, click_at, random_delay):
                        matches_detected += 1
                        self.update_matches(matches_detected)
                        self.update_status("Match! Keep going...")
                        debug_logger.log(f"Post-like match dismissed! Total: {matches_detected}")

                # Long pause injection (every N likes, pause like reading a profile)
                if sent >= next_long_pause:
                    pause_duration = random.uniform(*self.LONG_PAUSE_DURATION)
                    debug_logger.log(f"Long pause: {pause_duration:.1f}s (after {sent} likes)")
                    self.update_status(f"Reading profile... ({pause_duration:.0f}s)")
                    if not random_delay(pause_duration, pause_duration + 0.1,
                                       should_stop=self._should_stop):
                        break
                    next_long_pause = sent + random.randint(*self.LONG_PAUSE_INTERVAL)

                # Normal inter-like delay
                min_d, max_d = self.get_delay_range()
                self.update_status("Waiting...")
                if not random_delay(min_d, max_d, should_stop=self._should_stop):
                    break

            except FileNotFoundError as e:
                debug_logger.log(f"ERROR: Missing template: {e}")
                self.update_status(f"Missing template!")
                consecutive_failures += 1
                time.sleep(2)
            except Exception as e:
                debug_logger.log(f"ERROR: {e}")
                import traceback
                debug_logger.log(traceback.format_exc())
                self.update_status(f"Error: {str(e)[:50]}")
                consecutive_failures += 1
                time.sleep(1)

        # Session complete
        debug_logger.log(f"Session complete. Likes: {sent}, Matches: {matches_detected}")
        debug_logger.end_session()

        def finish():
            count_text = f"{sent}" if max_likes < 0 else f"{sent} / {max_likes}"
            self.count_var.set(count_text)
            match_text = f"Matches: {matches_detected}" if matches_detected > 0 else ""
            self.match_count_var.set(match_text)
            self.status_var.set(f"Done! ({sent} likes, {matches_detected} matches)")
            self.start_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.running = False

        self.root.after(0, finish)


def main():
    if '--version' in sys.argv:
        print("TinderTapper v0.1.0")
        print(f"  Python: {platform.python_version()} ({sys.executable})")
        print(f"  Frozen: {getattr(sys, 'frozen', False)}")
        return

    if '--capture' in sys.argv:
        from mirror import find_iphone_window, capture_window
        w = find_iphone_window()
        if w:
            img = capture_window(w['id'])
            if img:
                path = '/tmp/tinder_capture.png'
                img.save(path)
                print(f"Saved {img.size[0]}x{img.size[1]} to {path}")
                print("Open this image and crop template regions.")
            else:
                print("Capture failed - check Screen Recording permission")
        else:
            print("No iPhone Mirroring window found")
        return

    root = tk.Tk()
    style = ttk.Style()
    if 'aqua' in style.theme_names():
        style.theme_use('aqua')

    app = TinderTapperApp(root)

    def on_closing():
        if app.running:
            if messagebox.askokcancel("Quit", "Liker is running. Stop and quit?"):
                app.running = False
                root.after(500, root.destroy)
        else:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == '__main__':
    main()
