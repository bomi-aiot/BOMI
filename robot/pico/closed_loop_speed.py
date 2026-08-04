from machine import Pin, PWM, I2C
import machine
import math
import rp2
import sys
import time
import uselect

# =========================================================
# 좌우 엔코더 폐루프 속도 제어
#
# PWM 퍼센트가 아니라 목표 회전 속도(rev/s)로 명령한다.
# 실제 속도를 엔코더로 재서 PWM을 계속 고쳐 넣으므로
# 좌우 모터 개체차, 배터리 전압 강하, 바닥 마찰 변화를
# 트림 상수 없이 흡수한다.
#
# 시리얼 형식은 robot/docs/pico-serial-protocol.md가 정한다.
# 명령과 출력을 바꿀 때는 그 문서를 먼저 고친다.
#
# 노드가 쓰는 명령
#   V 0.3 0.3      좌우 목표 속도 (rev/s). 보낼 때마다 워치독을 다시 감는다
#   S              즉시 정지
#   T 0 | T 1      텔레메트리 끄기/켜기
#   P              프로토콜 버전과 펌웨어 이름 응답
#
# 사람이 쓰는 명령
#   D              시연 시퀀스 자동 실행 (전진·좌우회전·후진·360도)
#   R 0.3 0.3 10   10초간 주행 후 자동 정지 (튜닝용)
#   F 0.3          양쪽 같은 속도
#   G 15 80        속도 Kp, Ki 변경
#   Y 0.01 0.004   방향 유지 Kp, Ki 변경 (0 0 이면 끔)
#   W              엔코더 누적 카운트 1회 출력
#   C              엔코더 누적 카운트를 0으로
#   Z              주행 거리와 yaw를 0으로
#   E              현재 상태 1회 출력
#   H              도움말
#
# 출력은 첫 낱말로 종류를 밝힌다. T는 텔레메트리, ACK/ERR/WARN은
# 명령 응답과 오류이고, #으로 시작하는 줄은 사람이 읽는 글이다.
# 노드는 #과 빈 줄을 버린다.
# =========================================================

# 제어 주기
CONTROL_MS = 20

# 속도 측정 창. CONTROL_MS * VELOCITY_WINDOW 만큼을 본다.
# 0.3 rev/s에서 약 29카운트가 들어와 양자화 오차가 3% 수준이 된다.
VELOCITY_WINDOW = 5

# 프로토콜 버전과 펌웨어 이름. P 명령이 응답한다.
# 텔레메트리 필드를 늘리면 버전을 올린다.
PROTOCOL_VERSION = 1
FIRMWARE_NAME = "closed_loop_speed"

# 텔레메트리 출력 주기.
#
# 20ms 안에 16낱말 문자열을 만들어 내보낼 수 있는지는 아직
# 실기에서 재보지 않았다. 못 버티면 40ms(25Hz)로 내린다.
TELEMETRY_MS = 20

# V, F 명령은 이 시간 안에 다시 오지 않으면 정지한다.
#
# 노드가 20ms 주기로 V를 보내므로 프레임 15개 유실까지 견딘다.
WATCHDOG_MS = 300

# R 명령으로 지정할 수 있는 최대 주행 시간
MAX_RUN_SECONDS = 20.0

# 출력 제한
MIN_PERCENT = 0.0
MAX_PERCENT = 70.0

# 목표 속도 허용 범위
#
# 피드포워드로 0.8 rev/s는 약 54%가 필요하다.
# MAX_PERCENT까지 16% 여유가 남아 PI가 보정할 공간이 된다.
MAX_TARGET_REV_S = 0.8

# PI 게인. G 명령으로 주행 중에 바꿀 수 있다.
#
# 노이즈를 완전히 막을 수 없으므로 적분이 한 번 틀어졌을 때
# 빨리 되돌아오는 쪽이 중요하다. 출렁이면 G로 낮춘다.
KP = 15.0
KI = 80.0

# =========================================================
# 엔코더 노이즈 대책
#
# RR(GP6)에서 물리적으로 불가능한 속도가 간헐적으로 관측됐다.
# PWM 듀티가 바뀔 때 전류 급변이 신호선에 유도되는 것으로 보인다.
# 근본 대책은 배선이며 아래 둘은 제어가 흔들리지 않게 하는 방어책이다.
# =========================================================

# 상승 에지 후 이 시간만큼 무시한다. 0이면 필터 없음.
# 최고 속도에서도 에지 간격이 약 568us라 진짜 신호는 먹지 않는다.
DEBOUNCE_US = 100

# 같은 쪽 두 바퀴 중 하나가 다른 쪽의 이 배수를 넘으면
# 튀는 값으로 보고 그 틱의 값을 버린다.
# 노이즈는 카운트를 더하기만 하므로 빠른 쪽이 의심 대상이다.
#
# 정상 상태의 앞뒤 차이는 최대 1.2배 정도였다.
# 1.6으로 뒀더니 1.58배 스파이크가 통과해 적분을 망가뜨렸다.
OUTLIER_RATIO = 1.35

# 목표 속도의 이 배수를 넘는 값은 다른 바퀴와 비교할 것도 없이 버린다.
# 모터가 낼 수 있는 속도를 넘어서는 값은 측정 오류다.
ABSOLUTE_RATIO = 1.5

# 값을 버렸을 때는 직전 속도를 그대로 쓴다.
#
# 느린 쪽 값으로 대체하면 평균보다 낮게 잡혀서 제어기가
# PWM을 과하게 올리고, 그쪽이 빨라져 로봇이 반대로 꺾인다.
# 직전 값을 유지하면 그런 편향이 생기지 않는다.
# 다만 계속 버릴 수는 없으므로 이 틱 수를 넘으면 느린 쪽으로 넘어간다.
MAX_FREEZE_TICKS = 10

# 바닥 시험으로 측정한 바퀴 1회전당 이동 거리
DISTANCE_PER_REV_M = 0.1929

# =========================================================
# IMU (MPU-9250, SparkFun SEN-13762)
#
# 엔코더는 바퀴 회전만 본다. 바퀴 지름 차이나 슬립은
# 잡지 못하므로 실제 방향은 자이로로 따로 측정한다.
# =========================================================
IMU_SDA_PIN = 26
IMU_SCL_PIN = 27
IMU_ADDRESS = 0x68

# 동작이 확인된 imu_auto_left_turn_test_ok.py와 같은 100kHz를 쓴다.
# 400kHz에서는 모터 구동 중 ETIMEDOUT이 발생했다.
IMU_FREQUENCY = 100000

# 연속으로 이만큼 읽기에 실패하면 yaw를 끄고 주행만 이어간다.
# 주행 중 예외로 프로그램이 죽으면 그 자체가 위험하다.
MAX_IMU_ERRORS = 20

MPU_PWR_MGMT_1 = 0x6B
MPU_GYRO_CONFIG = 0x1B
MPU_GYRO_ZOUT_H = 0x47

# +-250 deg/s 설정에서의 감도
GYRO_SCALE = 131.0

# 이 값보다 작은 각속도는 노이즈로 보고 버린다
GYRO_DEADBAND = 0.5

# 시작할 때 자이로 영점을 잡는 시간
GYRO_CALIBRATION_SECONDS = 2.0

# =========================================================
# IMU 방향 유지
#
# 좌우 바퀴 속도를 완벽히 맞춰도 로봇은 휜다. 바퀴 지름 차이와
# 슬립은 엔코더에 잡히지 않기 때문이다. 실측에서 1.73m 주행에
# 매번 +1.2 ~ +1.9도씩 오른쪽으로 돌아갔다.
#
# yaw 오차를 좌우 목표 속도의 차이로 바꿔서 되돌린다.
# =========================================================

# 1도 벗어났을 때 좌우에 줄 속도 차이 (rev/s)
HEADING_KP = 0.010

# 적분 이득. 일정한 편향을 완전히 없애려면 필요하다.
HEADING_KI = 0.004

# 출발 직후에는 모터 반작용으로 몸이 흔들린다.
# 이 시간이 지난 뒤의 방향을 기준으로 삼는다.
HEADING_SETTLE_SECONDS = 0.7

# 보정량 제한. 폭주를 막는다.
MAX_HEADING_CORRECTION = 0.15

# 적분 누적 제한 (deg * s)
MAX_HEADING_INTEGRAL = 40.0

# =========================================================
# 시연용 자동 주행
#
# D 명령으로 시작한다. 거리와 각도로 각 구간을 끝내므로
# 엔코더와 IMU가 실제로 쓰이는 것을 그대로 보여준다.
# 출발한 자리, 출발한 방향으로 돌아온다.
# =========================================================

DEMO_FORWARD_SPEED = 0.5
DEMO_TURN_SPEED = 0.35

# 목표 각도에 이만큼 남으면 절반 속도로 줄인다
DEMO_SLOW_ZONE_DEG = 30.0

# 관성으로 더 도는 만큼 미리 끊는다. 오버슛이 크면 늘린다.
DEMO_TURN_LEAD_DEG = 10.0

# 한 구간이 이 시간을 넘으면 다음으로 넘어간다
DEMO_STEP_TIMEOUT_SECONDS = 20.0

# (종류, 값, 설명)
#   forward : 값 = 이동 거리 m (음수면 후진)
#   turn    : 값 = 회전 각도 deg (음수가 좌회전, 양수가 우회전)
#   pause   : 값 = 정지 시간 초
#
# 1m 직선 공간만 있으면 되고, 끝나면 출발한 자리와 방향으로 돌아온다.
DEMO_STEPS = [
    ("forward", 1.0, "forward 1m"),
    ("pause", 1.5, "stop"),
    ("turn", 90.0, "turn RIGHT 90"),
    ("pause", 1.5, "stop"),
    ("turn", -90.0, "turn LEFT 90, back to heading"),
    ("pause", 1.5, "stop"),
    ("forward", -1.0, "backward 1m, back to start"),
    ("pause", 1.5, "stop"),
    ("turn", -360.0, "spin LEFT 360"),
]

# =========================================================
# 피드포워드
#
# side_speed_curve.py로 측정한 무부하 직선이다.
# 바닥에서는 부하 때문에 조금 모자라며 그 차이는 PI가 메운다.
# =========================================================
LEFT_FF_INTERCEPT = 3.183
LEFT_FF_SLOPE = 62.980

RIGHT_FF_INTERCEPT = 4.033
RIGHT_FF_SLOPE = 55.476

# 손으로 한 바퀴 돌려 측정한 값
LF_CPR = 979
LR_CPR = 984
RF_CPR = 979
RR_CPR = 970

# =========================================================
# 핀
# =========================================================
LF_C1 = Pin(12, Pin.IN, Pin.PULL_UP)
LR_C1 = Pin(14, Pin.IN, Pin.PULL_UP)
RF_C1 = Pin(10, Pin.IN, Pin.PULL_UP)
RR_C1 = Pin(6, Pin.IN, Pin.PULL_UP)

# C2는 방향 판정에 쓴다. C1이 올라가는 순간의 C2 값이 방향을 알려준다.
LF_C2 = Pin(13, Pin.IN, Pin.PULL_UP)
LR_C2 = Pin(9, Pin.IN, Pin.PULL_UP)
RF_C2 = Pin(11, Pin.IN, Pin.PULL_UP)
RR_C2 = Pin(7, Pin.IN, Pin.PULL_UP)

# 바퀴마다 배선 순서가 달라 부호가 뒤집힐 수 있다.
# 손으로 앞으로 돌렸을 때 카운트가 줄어드는 바퀴가 있으면
# 그 자리를 -1로 바꾼다. 순서는 LF, LR, RF, RR.
ENCODER_DIRECTION = [1, 1, 1, 1]

# main.py가 걸어둔 IRQ는 Ctrl-C로 중단해도 남는다.
for encoder_pin in (LF_C1, LR_C1, RF_C1, RR_C1):
    encoder_pin.irq(handler=None)

right_dir = Pin(2, Pin.OUT)
right_pwm = PWM(Pin(3))

left_dir = Pin(4, Pin.OUT)
left_pwm = PWM(Pin(5))

right_pwm.freq(20000)
left_pwm.freq(20000)

RIGHT_FORWARD_DIR = 1
LEFT_FORWARD_DIR = 1


def duty_from_percent(percent):
    percent = max(0.0, min(100.0, percent))
    return int(percent * 65535 / 100)


def apply_left(percent, forward):
    """왼쪽 채널에 PWM과 방향을 적용한다."""
    if percent <= 0.0:
        left_pwm.duty_u16(0)
        return

    if forward:
        left_dir.value(LEFT_FORWARD_DIR)
    else:
        left_dir.value(1 - LEFT_FORWARD_DIR)

    left_pwm.duty_u16(duty_from_percent(percent))


def apply_right(percent, forward):
    """오른쪽 채널에 PWM과 방향을 적용한다."""
    if percent <= 0.0:
        right_pwm.duty_u16(0)
        return

    if forward:
        right_dir.value(RIGHT_FORWARD_DIR)
    else:
        right_dir.value(1 - RIGHT_FORWARD_DIR)

    right_pwm.duty_u16(duty_from_percent(percent))


def stop_motors():
    left_pwm.duty_u16(0)
    right_pwm.duty_u16(0)


# =========================================================
# PIO 엔코더
# =========================================================

@rp2.asm_pio()
def count_edges_directional():
    """C1 상승 에지마다 그 순간의 C2 값을 FIFO로 보낸다.

    C2가 0이면 0을, 1이면 1을 보낸다. CPU가 이 값을 보고
    정방향인지 역방향인지 판정한다.
    """
    wrap_target()

    wait(0, pin, 0)
    wait(1, pin, 0)

    jmp(pin, "c2_high")

    set(x, 0)
    mov(isr, x)
    push(noblock)
    jmp("done")

    label("c2_high")
    set(x, 1)
    mov(isr, x)
    push(noblock)

    label("done")

    wrap()


@rp2.asm_pio()
def count_edges_directional_debounced():
    """방향 판정에 100us 블랭킹을 더한 것."""
    wrap_target()

    wait(0, pin, 0)
    wait(1, pin, 0)

    jmp(pin, "c2_high")

    set(x, 0)
    mov(isr, x)
    push(noblock)
    jmp("blank_start")

    label("c2_high")
    set(x, 1)
    mov(isr, x)
    push(noblock)

    # 25회 * 4사이클 = 100사이클, 1MHz에서 100us 무시
    label("blank_start")
    set(x, 24)

    label("blank")
    jmp(x_dec, "blank") [3]

    wrap()


PIO0_FDEBUG = 0x50200000 + 0x008
RXSTALL_SHIFT = 16


def clear_rxstall():
    machine.mem32[PIO0_FDEBUG] = 0x0F << RXSTALL_SHIFT


def rxstall_flags():
    value = machine.mem32[PIO0_FDEBUG]

    return [
        (value >> (RXSTALL_SHIFT + index)) & 1
        for index in range(4)
    ]


# =========================================================
# IMU
# =========================================================

imu = None
imu_available = False
gyro_offset = 0.0

# 연속 읽기 실패 횟수와 주행 중 누적 실패 횟수
imu_error_streak = 0
imu_error_total = 0


def imu_write(register, value):
    imu.writeto_mem(IMU_ADDRESS, register, bytes([value]))


def read_gyro_z():
    """자이로 Z축 각속도를 deg/s로 읽는다."""
    data = imu.readfrom_mem(IMU_ADDRESS, MPU_GYRO_ZOUT_H, 2)

    value = (data[0] << 8) | data[1]

    if value & 0x8000:
        value -= 65536

    return value / GYRO_SCALE


def read_gyro_z_safe():
    """자이로를 읽되 통신 오류면 None을 돌려준다.

    모터 노이즈로 I2C가 간헐적으로 끊기므로 주행 중에
    예외가 밖으로 나가면 안 된다.
    """
    try:
        return read_gyro_z()
    except OSError:
        return None


def setup_imu():
    """IMU를 깨우고 자이로 영점을 측정한다.

    장치를 못 찾으면 yaw 기능만 끄고 나머지는 그대로 둔다.
    """
    global imu, imu_available, gyro_offset

    try:
        imu = I2C(
            1,
            sda=Pin(IMU_SDA_PIN),
            scl=Pin(IMU_SCL_PIN),
            freq=IMU_FREQUENCY
        )

        if IMU_ADDRESS not in imu.scan():
            print("WARN IMU not found at 0x68, yaw disabled")
            return

        imu_write(MPU_PWR_MGMT_1, 0x00)
        time.sleep_ms(100)

        imu_write(MPU_GYRO_CONFIG, 0x00)
        time.sleep_ms(50)

        print("#")
        print("# Keep the robot completely still.")
        print("# Calibrating gyro for {} seconds...".format(
            GYRO_CALIBRATION_SECONDS
        ))

        samples = int(GYRO_CALIBRATION_SECONDS * 100)
        total = 0.0

        for _ in range(samples):
            total += read_gyro_z()
            time.sleep_ms(10)

        gyro_offset = total / samples
        imu_available = True

        print("# Gyro offset: {:.4f} deg/s".format(gyro_offset))

    except Exception as error:
        print("WARN IMU init failed, yaw disabled:", error)
        imu_available = False


def clear_fifo(sm):
    while sm.rx_fifo() > 0:
        sm.get()


def read_fifo_signed(sm, direction):
    """FIFO에 쌓인 에지를 방향까지 반영해서 합산한다.

    PIO가 보낸 값이 0이면 한 방향, 1이면 반대 방향이다.
    어느 쪽이 전진인지는 배선에 따라 다르므로
    ENCODER_DIRECTION으로 바퀴마다 뒤집는다.
    """
    total = 0

    while sm.rx_fifo() > 0:
        if sm.get() == 0:
            total += 1
        else:
            total -= 1

    return total * direction


wheel_pins = [LF_C1, LR_C1, RF_C1, RR_C1]
wheel_c2_pins = [LF_C2, LR_C2, RF_C2, RR_C2]
wheel_cpr = [LF_CPR, LR_CPR, RF_CPR, RR_CPR]

if DEBOUNCE_US > 0:
    pio_program = count_edges_directional_debounced
else:
    pio_program = count_edges_directional

state_machines = [
    rp2.StateMachine(
        index,
        pio_program,
        freq=1_000_000,
        in_base=wheel_pins[index],
        jmp_pin=wheel_c2_pins[index]
    )
    for index in range(4)
]


# =========================================================
# PI 제어기
# =========================================================

class SideController:
    """한쪽 바퀴 묶음의 속도를 PI로 추종한다.

    출력은 PWM 퍼센트이며 피드포워드 직선을 기준으로
    오차만큼을 더한다. 출력이 한계에 붙으면 적분을
    멈춰서 적분 폭주를 막는다.
    """

    def __init__(self, name, ff_intercept, ff_slope):
        self.name = name
        self.ff_intercept = ff_intercept
        self.ff_slope = ff_slope

        self.integral = 0.0
        self.target = 0.0
        self.measured = 0.0
        self.output = 0.0

    def reset(self):
        """정지하거나 목표가 0이 될 때 내부 상태를 지운다."""
        self.integral = 0.0
        self.output = 0.0
        self.measured = 0.0

    def update(self, target, measured, dt):
        """목표와 실측으로 다음 PWM 퍼센트를 계산한다."""
        self.target = target
        self.measured = measured

        if target <= 0.0:
            self.reset()
            return 0.0

        error = target - measured

        feedforward = (
            self.ff_intercept
            + self.ff_slope * target
        )

        candidate = (
            feedforward
            + KP * error
            + KI * self.integral
        )

        # 출력이 한계 밖으로 나가는 방향으로는 적분하지 않는다
        saturated_high = (
            candidate >= MAX_PERCENT and error > 0
        )
        saturated_low = (
            candidate <= MIN_PERCENT and error < 0
        )

        if not saturated_high and not saturated_low:
            self.integral += error * dt

            candidate = (
                feedforward
                + KP * error
                + KI * self.integral
            )

        self.output = max(
            MIN_PERCENT,
            min(MAX_PERCENT, candidate)
        )

        return self.output


left_controller = SideController(
    "L",
    LEFT_FF_INTERCEPT,
    LEFT_FF_SLOPE
)

right_controller = SideController(
    "R",
    RIGHT_FF_INTERCEPT,
    RIGHT_FF_SLOPE
)


# =========================================================
# 상태
# =========================================================

wheel_counts = [0, 0, 0, 0]

# 슬라이딩 윈도우용 바퀴별 회전량 기록
#
# 칸 수는 정확히 VELOCITY_WINDOW개다. 덮어쓰기 직전의 칸이
# VELOCITY_WINDOW 틱 전 값을 담고 있으므로 측정 구간이
# CONTROL_MS * VELOCITY_WINDOW와 정확히 일치한다.
wheel_history = [
    [0.0] * VELOCITY_WINDOW
    for _ in range(4)
]

wheel_speeds = [0.0, 0.0, 0.0, 0.0]

# 이상치를 걸러낸 좌우 실측 속도. 부호가 있다.
# 텔레메트리의 l_act, r_act가 이 값이다.
side_speeds = [0.0, 0.0]

# 지난 텔레메트리 이후 있었던 일을 모아 두는 플래그.
# print_telemetry가 flags 필드로 소비하면서 각각 지운다.
fifo_overflow_flag = False
outlier_flag = False

# 이상치로 버린 횟수. 배선 문제의 심각도를 보는 지표다.
rejected_counts = [0, 0, 0, 0]

# 값을 버렸을 때 되돌려 쓸 직전 속도와 연속 버림 횟수
last_side_speed = [0.0, 0.0]
freeze_ticks = [0, 0]

history_index = 0
history_filled = 0

# 주행 누적값. R 명령이나 Z 명령에서 초기화한다.
travel_distance_m = 0.0
yaw_degrees = 0.0
lateral_offset_m = 0.0

# 자이로 z축 각속도. 텔레메트리의 rate 필드다.
# IMU를 못 읽는 동안에는 갱신되지 않는다.
gyro_rate_dps = 0.0

# 방향 유지 상태
heading_kp = HEADING_KP
heading_ki = HEADING_KI
heading_integral = 0.0
heading_correction = 0.0

# 출발 직후 흔들림이 가라앉고 기준 방향을 잡았는지
heading_ready = False
run_start_ms = time.ticks_ms()

# 시연 진행 상태
demo_active = False
demo_index = 0
demo_started = False
demo_step_start_ms = time.ticks_ms()

left_target = 0.0
right_target = 0.0

left_forward = True
right_forward = True

telemetry_on = True

# 이 시각이 지나면 무조건 정지한다.
# V, F는 WATCHDOG_MS 뒤로, R은 지정한 시간 뒤로 설정한다.
deadline_ms = time.ticks_ms()
motors_running = False

# 마감 시각이 워치독인지 R의 지정 시간인지 구분한다.
# 워치독으로 멈춘 것만 ERR watchdog을 내고 플래그를 세운다.
deadline_is_watchdog = False

# 워치독으로 멈췄다. 다음 V 명령이 오면 내려간다.
watchdog_tripped = False


def update_wheel_speeds(window_seconds):
    """바퀴 4개의 속도를 갱신하고 좌우 평균을 돌려준다."""
    global history_index, history_filled

    revolutions = [
        wheel_counts[index] / wheel_cpr[index]
        for index in range(4)
    ]

    if history_filled >= VELOCITY_WINDOW:
        for index in range(4):
            wheel_speeds[index] = (
                revolutions[index]
                - wheel_history[index][history_index]
            ) / window_seconds
    else:
        for index in range(4):
            wheel_speeds[index] = 0.0

    for index in range(4):
        wheel_history[index][history_index] = revolutions[index]

    history_index = (history_index + 1) % VELOCITY_WINDOW
    history_filled += 1

    left_speed = combine_side(0, 0, 1, left_target)
    right_speed = combine_side(1, 2, 3, right_target)

    # 텔레메트리가 쓸 수 있게 남긴다
    side_speeds[0] = left_speed
    side_speeds[1] = right_speed

    return left_speed, right_speed


def update_odometry(left_speed, right_speed, dt):
    """주행 거리, yaw, 횡오차를 누적한다.

    거리는 이상치를 걸러낸 좌우 속도로 적분한다.
    원시 카운트를 쓰면 노이즈 스파이크가 거리에 그대로 섞인다.

    속도에 부호가 있으므로 후진하면 거리가 줄어든다.
    앞뒤로 왔다 갔다 하면 제자리로 돌아온다.

    yaw는 자이로 적분값이며 오른쪽 회전이 양수다.
    횡오차는 진행 방향 기준 오른쪽으로 벗어난 거리다.
    """
    global travel_distance_m, yaw_degrees, lateral_offset_m
    global imu_available, imu_error_streak, imu_error_total
    global gyro_rate_dps

    average_speed = (left_speed + right_speed) / 2

    step_distance = (
        average_speed * DISTANCE_PER_REV_M * dt
    )

    travel_distance_m += step_distance

    if not imu_available:
        return

    rate = read_gyro_z_safe()

    if rate is None:
        imu_error_streak += 1
        imu_error_total += 1

        if imu_error_streak >= MAX_IMU_ERRORS:
            imu_available = False
            print("WARN IMU read failed repeatedly, yaw disabled")

        return

    imu_error_streak = 0

    rate -= gyro_offset

    if abs(rate) < GYRO_DEADBAND:
        rate = 0.0

    gyro_rate_dps = rate
    yaw_degrees += rate * dt

    lateral_offset_m += step_distance * math.sin(
        math.radians(yaw_degrees)
    )


def reset_odometry():
    """주행 누적값을 0으로 되돌린다."""
    global travel_distance_m, yaw_degrees, lateral_offset_m

    travel_distance_m = 0.0
    yaw_degrees = 0.0
    lateral_offset_m = 0.0


def reset_heading_reference():
    """지금 향한 방향을 직진 기준으로 삼는다."""
    global yaw_degrees, lateral_offset_m, heading_integral

    yaw_degrees = 0.0
    lateral_offset_m = 0.0
    heading_integral = 0.0


def update_heading(dt):
    """yaw 오차를 좌우 속도 보정량으로 바꾼다.

    yaw가 양수면 오른쪽으로 틀어진 것이므로 왼쪽을 늦추고
    오른쪽을 올려서 왼쪽으로 되돌린다.

    비례항만 쓰면 일정한 편향이 남는다. 지금은 바퀴 지름 차이처럼
    원인이 계속 작용하므로 적분항이 있어야 0으로 수렴한다.
    """
    global heading_integral, heading_correction, heading_ready

    if not motors_running or not imu_available:
        heading_correction = 0.0
        return

    # 앞으로 곧게 갈 때만 보정한다.
    #
    # 목표는 크기로만 저장되므로 제자리 회전(좌 -0.35, 우 +0.35)도
    # 크기만 보면 같아 보인다. 진행 방향까지 확인해야 한다.
    #
    # 이 판정이 기준 재설정보다 먼저 와야 한다. 회전 중에 yaw를
    # 0으로 되돌리면 회전 각도를 잴 수 없다.
    if not left_forward or not right_forward:
        heading_correction = 0.0
        return

    if left_target <= 0.0 or left_target != right_target:
        heading_correction = 0.0
        return

    if heading_kp <= 0.0 and heading_ki <= 0.0:
        heading_correction = 0.0
        return

    # 출발 직후에는 모터 반작용으로 몸이 흔들린다.
    # 가라앉기를 기다렸다가 그때 방향을 기준으로 잡는다.
    if not heading_ready:
        elapsed = time.ticks_diff(
            time.ticks_ms(),
            run_start_ms
        )

        if elapsed < int(HEADING_SETTLE_SECONDS * 1000):
            heading_correction = 0.0
            return

        reset_heading_reference()
        heading_ready = True

    heading_integral += yaw_degrees * dt

    heading_integral = max(
        -MAX_HEADING_INTEGRAL,
        min(MAX_HEADING_INTEGRAL, heading_integral)
    )

    correction = (
        heading_kp * yaw_degrees
        + heading_ki * heading_integral
    )

    heading_correction = max(
        -MAX_HEADING_CORRECTION,
        min(MAX_HEADING_CORRECTION, correction)
    )


def print_run_summary():
    """주행이 끝났을 때 거리와 방향 오차를 정리해 보여준다."""
    print("# --- RUN SUMMARY ---")
    print("# distance : {:.3f} m".format(travel_distance_m))

    if imu_available:
        print("# yaw      : {:+.2f} deg".format(yaw_degrees))
        print("# lateral  : {:+.1f} cm".format(
            lateral_offset_m * 100
        ))
        print("#   (plus is to the right)")
    else:
        print("# yaw      : IMU disabled")

    print("# rejected : {}".format(
        "/".join(str(count) for count in rejected_counts)
    ))
    print("# imu error: {}".format(imu_error_total))

    if heading_kp > 0.0 or heading_ki > 0.0:
        print("# heading  : hold on (kp={} ki={})".format(
            heading_kp,
            heading_ki
        ))
    else:
        print("# heading  : hold off")

    print("# -------------------")


def combine_side(side, front_index, rear_index, target):
    """같은 쪽 두 바퀴 속도를 하나로 합친다.

    두 가지로 이상치를 걸러낸다. 하나는 목표 대비 절대 상한이고
    다른 하나는 두 바퀴 사이의 비율이다. 걸리면 그 틱의 값을
    버리고 직전 속도를 유지한다. 느린 쪽으로 대체하면 평균보다
    낮게 잡혀 제어기가 과하게 반응한다.
    """
    global outlier_flag

    front = wheel_speeds[front_index]
    rear = wheel_speeds[rear_index]

    # 속도에 부호가 붙으므로 판정은 크기로 한다
    front_size = abs(front)
    rear_size = abs(rear)

    front_bad = False
    rear_bad = False

    # 목표를 알 때만 절대 상한을 적용한다
    if target > 0.0:
        limit = target * ABSOLUTE_RATIO

        front_bad = front_size > limit
        rear_bad = rear_size > limit

    lower = min(front_size, rear_size)
    higher = max(front_size, rear_size)

    # 정지 근처에서는 비율 판정이 의미가 없다
    if lower > 0.02 and higher > lower * OUTLIER_RATIO:
        if front_size > rear_size:
            front_bad = True
        else:
            rear_bad = True

    if not front_bad and not rear_bad:
        freeze_ticks[side] = 0
        last_side_speed[side] = (front + rear) / 2
        return last_side_speed[side]

    outlier_flag = True

    if front_bad:
        rejected_counts[front_index] += 1

    if rear_bad:
        rejected_counts[rear_index] += 1

    freeze_ticks[side] += 1

    # 너무 오래 얼려두면 실제 변화를 못 따라간다
    if freeze_ticks[side] <= MAX_FREEZE_TICKS:
        return last_side_speed[side]

    # 성한 바퀴가 하나라도 있으면 그 값을 쓰고,
    # 둘 다 이상하면 느린 쪽을 쓴다 (부호는 살린다)
    if front_bad and not rear_bad:
        value = rear
    elif rear_bad and not front_bad:
        value = front
    elif front_size <= rear_size:
        value = front
    else:
        value = rear

    last_side_speed[side] = value

    return value


def stop_all(reason, is_watchdog=False):
    """모터를 끄고 제어기 상태를 지운다.

    워치독으로 걸렸을 때만 ERR watchdog을 낸다. S 명령, R의 지정 시간
    경과, 시연 진행은 정상 정지이므로 ACK STOP으로 기록한다.
    """
    global left_target, right_target, motors_running
    global watchdog_tripped

    left_target = 0.0
    right_target = 0.0

    left_controller.reset()
    right_controller.reset()

    stop_motors()

    was_running = motors_running
    motors_running = False

    # S 명령이나 R의 지정 시간 경과처럼 정상 정지일 때는 이전 워치독
    # 표시를 지운다. 그대로 두면 재접속 직후 S로 안전 정지했는데도
    # flags 비트 2가 지난 세션의 워치독을 계속 가리키게 된다.
    watchdog_tripped = is_watchdog

    # 시연 중에는 구간마다 요약이 끼면 화면이 지저분해진다
    if demo_active:
        return

    if is_watchdog:
        print("ERR watchdog")
    else:
        print("ACK STOP", reason)

    if was_running:
        print_run_summary()


def start_demo():
    """시연 시퀀스를 처음부터 시작한다."""
    global demo_active, demo_index, demo_started

    if not imu_available:
        print("ERR demo needs the IMU, but it is disabled")
        return

    demo_active = True
    demo_index = 0
    demo_started = False

    print("#")
    print("# =========== DEMO START ===========")
    print("# steps:", len(DEMO_STEPS))
    print("# press S to abort")
    print("# ==================================")


def demo_tick():
    """시연 시퀀스를 한 단계씩 진행한다.

    각 구간은 시간이 아니라 실제로 이동한 거리나 회전한 각도로
    끝난다. 제어 루프에서 매 주기 호출되므로 중간에 S로 멈출 수 있다.
    """
    global demo_active, demo_index, demo_started
    global demo_step_start_ms, left_target, right_target

    if not demo_active:
        return

    if demo_index >= len(DEMO_STEPS):
        demo_active = False
        stop_all("demo finished")

        print("#")
        print("# =========== DEMO COMPLETE ===========")
        print("# The robot should be back at the start.")
        print("# =====================================")
        return

    kind, value, label = DEMO_STEPS[demo_index]

    # 구간 진입
    if not demo_started:
        demo_started = True
        demo_step_start_ms = time.ticks_ms()

        print("# [{}/{}] {}".format(
            demo_index + 1,
            len(DEMO_STEPS),
            label
        ))

        if kind == "forward":
            # 값이 음수면 후진. 후진 중에는 방향 유지가 동작하지 않는다.
            speed = DEMO_FORWARD_SPEED

            if value < 0:
                speed = -speed

            set_targets(
                speed,
                speed,
                DEMO_STEP_TIMEOUT_SECONDS
            )
        elif kind == "turn":
            if value < 0:
                # 좌회전: 왼쪽 후진, 오른쪽 전진
                set_targets(
                    -DEMO_TURN_SPEED,
                    DEMO_TURN_SPEED,
                    DEMO_STEP_TIMEOUT_SECONDS
                )
            else:
                set_targets(
                    DEMO_TURN_SPEED,
                    -DEMO_TURN_SPEED,
                    DEMO_STEP_TIMEOUT_SECONDS
                )
        else:
            stop_all("demo pause")

        reset_odometry()
        return

    elapsed_ms = time.ticks_diff(
        time.ticks_ms(),
        demo_step_start_ms
    )

    finished = False

    if kind == "forward":
        # 후진하면 거리가 음수로 쌓이므로 크기로 비교한다
        finished = abs(travel_distance_m) >= abs(value)

    elif kind == "turn":
        remaining = abs(value) - abs(yaw_degrees)

        if remaining <= DEMO_TURN_LEAD_DEG:
            finished = True
        elif remaining < DEMO_SLOW_ZONE_DEG:
            # 목표가 가까우면 감속해서 오버슛을 줄인다
            left_target = DEMO_TURN_SPEED * 0.5
            right_target = DEMO_TURN_SPEED * 0.5

    else:
        finished = elapsed_ms >= int(value * 1000)

    if elapsed_ms > int(DEMO_STEP_TIMEOUT_SECONDS * 1000):
        print("WARN step timeout, moving on")
        finished = True

    if not finished:
        return

    if kind == "forward":
        print("# moved {:.3f} m, yaw {:+.2f} deg".format(
            travel_distance_m,
            yaw_degrees
        ))
    elif kind == "turn":
        print("# turned {:+.2f} deg".format(yaw_degrees))

    if kind != "pause":
        stop_all("demo step")

    demo_index += 1
    demo_started = False


def print_help():
    print("# Commands:")
    print("#   V 0.3 0.3     left/right target rev per second")
    print("#   S             stop")
    print("#   T 0 | T 1     telemetry off/on")
    print("#   P             protocol version and firmware name")
    print("#   D             run the demo sequence")
    print("#   R 0.3 0.3 10  drive 10 seconds then stop")
    print("#   F 0.3         both sides same target")
    print("#   G 15 80       set speed Kp and Ki")
    print("#   Y 0.01 0.004  set heading Kp and Ki (0 0 = off)")
    print("#   W             print raw encoder counts")
    print("#   C             clear encoder counts")
    print("#   Z             reset distance and yaw")
    print("#   E             print state once")
    print("#   H             help")
    print("#   max target    {} rev/s".format(MAX_TARGET_REV_S))
    print("#   max output    {} percent".format(MAX_PERCENT))


def print_state():
    """사람이 보는 상태 한 줄을 출력한다. T 텔레메트리와는 다른 형식이다."""
    stall = rxstall_flags()

    print(
        "# L tgt={:.3f} act={:.3f} pwm={:5.2f} | "
        "R tgt={:.3f} act={:.3f} pwm={:5.2f} | "
        "lf={:.3f} lr={:.3f} rf={:.3f} rr={:.3f} | "
        "yaw={:+.2f} rate={:+.2f} cor={:+.3f} d={:.2f} | "
        "rej={} stall={}".format(
            left_controller.target,
            left_controller.measured,
            left_controller.output,
            right_controller.target,
            right_controller.measured,
            right_controller.output,
            wheel_speeds[0],
            wheel_speeds[1],
            wheel_speeds[2],
            wheel_speeds[3],
            yaw_degrees,
            gyro_rate_dps,
            heading_correction,
            travel_distance_m,
            "/".join(str(count) for count in rejected_counts),
            "".join(str(flag) for flag in stall)
        )
    )


def build_flags():
    """텔레메트리 flags 필드를 조립한다.

    fifo_overflow_flag와 outlier_flag는 지난 텔레메트리 이후 있었던 일을
    모아 둔 것이라, 여기서 읽으면서 지운다. 다음 줄은 그 사이의 새 일만
    반영한다.
    """
    global fifo_overflow_flag, outlier_flag

    value = 0

    if motors_running:
        value |= 0x01

    if imu_available:
        value |= 0x02

    if watchdog_tripped:
        value |= 0x04

    if fifo_overflow_flag:
        value |= 0x08
        fifo_overflow_flag = False

    if outlier_flag:
        value |= 0x10
        outlier_flag = False

    return value


def print_telemetry():
    """T로 시작하는 16낱말 텔레메트리 한 줄을 출력한다.

    형식은 robot/docs/pico-serial-protocol.md `## 4`가 정한다.
    """
    left_signed_target = left_target if left_forward else -left_target
    right_signed_target = right_target if right_forward else -right_target

    print(
        "T {} {:.3f} {:.3f} {:.3f} {:.3f} "
        "{} {} {} {} "
        "{:.1f} {:.1f} {:.2f} {:.2f} {:.2f} "
        "0x{:02x}".format(
            time.ticks_ms(),
            left_signed_target,
            side_speeds[0],
            right_signed_target,
            side_speeds[1],
            wheel_counts[0],
            wheel_counts[1],
            wheel_counts[2],
            wheel_counts[3],
            left_controller.output,
            right_controller.output,
            yaw_degrees,
            gyro_rate_dps,
            travel_distance_m,
            build_flags()
        )
    )


def parse_target(text):
    """목표 속도 문자열을 검사해서 float으로 바꾼다."""
    value = float(text)

    if value != value:
        raise ValueError("target must be a number")

    if abs(value) > MAX_TARGET_REV_S:
        raise ValueError(
            "target must be within +-{}".format(MAX_TARGET_REV_S)
        )

    return value


def set_targets(left_value, right_value, run_seconds, is_watchdog=False):
    """좌우 목표 속도와 주행 마감 시각을 설정한다.

    is_watchdog이 참이면 마감 시각을 통신 워치독으로 취급한다.
    V, F가 이렇게 부른다. R의 지정 시간과 시연 구간은 아니다.
    """
    global left_target, right_target
    global left_forward, right_forward
    global deadline_ms, deadline_is_watchdog, motors_running
    global watchdog_tripped
    global heading_ready, heading_integral, heading_correction
    global run_start_ms

    left_forward = left_value >= 0
    right_forward = right_value >= 0

    left_target = abs(left_value)
    right_target = abs(right_value)

    if left_target == 0.0:
        left_controller.reset()

    if right_target == 0.0:
        right_controller.reset()

    motors_running = left_target > 0.0 or right_target > 0.0

    # 새 주행이므로 방향 기준을 다시 잡는다
    heading_ready = False
    heading_integral = 0.0
    heading_correction = 0.0
    run_start_ms = time.ticks_ms()

    deadline_ms = time.ticks_add(
        time.ticks_ms(),
        int(run_seconds * 1000)
    )
    deadline_is_watchdog = is_watchdog
    watchdog_tripped = False

    print(
        "ACK V {:.3f} {:.3f} for {:.1f}s".format(
            left_value,
            right_value,
            run_seconds
        )
    )


def handle_command(command):
    global KP, KI, telemetry_on
    global heading_kp, heading_ki, heading_integral
    global demo_active

    command = command.strip()

    if not command:
        return

    parts = command.upper().split()
    cmd = parts[0]

    try:
        if cmd == "V":
            if len(parts) != 3:
                print("ERR usage: V <left> <right>")
                return

            set_targets(
                parse_target(parts[1]),
                parse_target(parts[2]),
                WATCHDOG_MS / 1000.0,
                is_watchdog=True
            )

        elif cmd == "F":
            if len(parts) != 2:
                print("ERR usage: F <rev_per_s>")
                return

            value = parse_target(parts[1])
            set_targets(
                value, value, WATCHDOG_MS / 1000.0, is_watchdog=True
            )

        elif cmd == "R":
            if len(parts) != 4:
                print("ERR usage: R <left> <right> <seconds>")
                return

            run_seconds = float(parts[3])

            if run_seconds <= 0 or run_seconds > MAX_RUN_SECONDS:
                print(
                    "ERR seconds must be within 0 to {}".format(
                        MAX_RUN_SECONDS
                    )
                )
                return

            # 한 번의 시험 주행이므로 누적값을 새로 시작한다
            reset_odometry()

            set_targets(
                parse_target(parts[1]),
                parse_target(parts[2]),
                run_seconds
            )

        elif cmd == "Y":
            if len(parts) != 3:
                print("ERR usage: Y <kp_yaw> <ki_yaw>")
                return

            new_kp = float(parts[1])
            new_ki = float(parts[2])

            if new_kp < 0 or new_ki < 0:
                print("ERR gains must not be negative")
                return

            heading_kp = new_kp
            heading_ki = new_ki
            heading_integral = 0.0

            if heading_kp == 0.0 and heading_ki == 0.0:
                print("ACK Y heading hold OFF")
            else:
                print("ACK Y {} {}".format(heading_kp, heading_ki))

        elif cmd == "W":
            # 손으로 바퀴를 돌려 방향 판정을 확인할 때 쓴다.
            # 앞으로 돌리면 값이 커져야 한다.
            print(
                "# counts LF={} LR={} RF={} RR={}".format(
                    wheel_counts[0],
                    wheel_counts[1],
                    wheel_counts[2],
                    wheel_counts[3]
                )
            )

        elif cmd == "C":
            for index in range(4):
                wheel_counts[index] = 0

            print("ACK C counts cleared")

        elif cmd == "Z":
            reset_odometry()
            print("ACK Z")

        elif cmd == "D":
            telemetry_on = False
            start_demo()

        elif cmd == "S":
            if demo_active:
                demo_active = False
                print("# DEMO ABORTED")

            stop_all("command")

        elif cmd == "G":
            if len(parts) != 3:
                print("ERR usage: G <kp> <ki>")
                return

            new_kp = float(parts[1])
            new_ki = float(parts[2])

            if new_kp < 0 or new_ki < 0:
                print("ERR gains must not be negative")
                return

            KP = new_kp
            KI = new_ki

            left_controller.integral = 0.0
            right_controller.integral = 0.0

            print("ACK G {} {}".format(KP, KI))

        elif cmd == "T":
            if len(parts) != 2 or parts[1] not in ("0", "1"):
                print("ERR usage: T <0|1>")
                return

            telemetry_on = parts[1] == "1"
            print("ACK T", "on" if telemetry_on else "off")

        elif cmd == "P":
            print(
                "ACK P proto={} fw={}".format(
                    PROTOCOL_VERSION,
                    FIRMWARE_NAME
                )
            )

        elif cmd == "E":
            print_state()

        elif cmd == "H":
            print_help()

        else:
            print("ERR unknown command:", command)

    except ValueError as error:
        print("ERR", error)


# =========================================================
# 메인 루프
# =========================================================

poller = uselect.poll()
poller.register(sys.stdin, uselect.POLLIN)

input_buffer = ""

try:
    stop_motors()

    for sm in state_machines:
        sm.active(1)
        clear_fifo(sm)

    clear_rxstall()

    setup_imu()
    reset_odometry()

    print("#")
    print("# BOMI closed loop speed controller")
    print("# Control: {} ms, velocity window: {} ms".format(
        CONTROL_MS,
        CONTROL_MS * VELOCITY_WINDOW
    ))
    print("# Watchdog: {} ms".format(WATCHDOG_MS))
    print_help()

    now_ms = time.ticks_ms()
    next_control_ms = time.ticks_add(now_ms, CONTROL_MS)
    next_telemetry_ms = time.ticks_add(now_ms, TELEMETRY_MS)

    control_dt = CONTROL_MS / 1000.0
    window_seconds = control_dt * VELOCITY_WINDOW

    while True:
        # ---------------------------------------------
        # FIFO는 매 반복마다 비운다.
        # 4단뿐이라 제어 주기까지 기다리면 넘친다.
        # ---------------------------------------------
        for index in range(4):
            wheel_counts[index] += read_fifo_signed(
                state_machines[index],
                ENCODER_DIRECTION[index]
            )

        if any(rxstall_flags()):
            fifo_overflow_flag = True
            clear_rxstall()

        # ---------------------------------------------
        # 시리얼 명령
        # ---------------------------------------------
        if poller.poll(0):
            char = sys.stdin.read(1)

            if char in ("\r", "\n"):
                if input_buffer:
                    handle_command(input_buffer)
                    input_buffer = ""
            else:
                input_buffer += char

        now_ms = time.ticks_ms()

        # ---------------------------------------------
        # 제어 주기
        # ---------------------------------------------
        if time.ticks_diff(now_ms, next_control_ms) >= 0:
            next_control_ms = time.ticks_add(
                next_control_ms,
                CONTROL_MS
            )

            left_speed, right_speed = update_wheel_speeds(
                window_seconds
            )

            update_odometry(left_speed, right_speed, control_dt)
            update_heading(control_dt)
            demo_tick()

            # 방향 보정을 반영한 실제 목표
            left_goal = max(
                0.0,
                min(
                    MAX_TARGET_REV_S,
                    left_target - heading_correction
                )
            )

            right_goal = max(
                0.0,
                min(
                    MAX_TARGET_REV_S,
                    right_target + heading_correction
                )
            )

            # 목표는 크기값이므로 제어기에도 크기를 준다.
            # 방향은 apply_left/apply_right가 따로 처리한다.
            left_output = left_controller.update(
                left_goal,
                abs(left_speed),
                control_dt
            )

            right_output = right_controller.update(
                right_goal,
                abs(right_speed),
                control_dt
            )

            apply_left(left_output, left_forward)
            apply_right(right_output, right_forward)

        # ---------------------------------------------
        # 마감 시각이 지나면 정지
        #
        # V, F는 명령이 계속 오지 않으면 여기서 걸리고 워치독으로 취급한다.
        # R과 시연 구간은 지정한 시간이 끝나면 걸리며 정상 정지다.
        # ---------------------------------------------
        if motors_running:
            if time.ticks_diff(now_ms, deadline_ms) >= 0:
                if deadline_is_watchdog:
                    stop_all("watchdog", is_watchdog=True)
                else:
                    stop_all("deadline")

        # ---------------------------------------------
        # 텔레메트리. 주행 여부와 무관하게 항상 보낸다.
        # ---------------------------------------------
        if telemetry_on:
            if time.ticks_diff(
                now_ms,
                next_telemetry_ms
            ) >= 0:
                next_telemetry_ms = time.ticks_add(
                    now_ms,
                    TELEMETRY_MS
                )

                print_telemetry()

except KeyboardInterrupt:
    print("# KeyboardInterrupt")

except Exception as error:
    # 예기치 못한 오류로 끝나도 아래 finally에서 모터는 반드시 꺼진다.
    print("ERR", error)

finally:
    stop_motors()

    # 주행 중에 끝났더라도 그때까지의 결과는 남긴다
    if motors_running:
        motors_running = False
        print_run_summary()

    for sm in state_machines:
        sm.active(0)

    left_pwm.deinit()
    right_pwm.deinit()

    print("# Motor output is OFF")
