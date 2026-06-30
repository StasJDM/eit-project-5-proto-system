"""Lightweight internationalisation module.

Usage:
    from app.i18n import t, i18n

    # In widget constructor:
    self.setText(t("btn_start"))

    # React to language changes:
    i18n.language_changed.connect(self.retranslate)

    def retranslate(self):
        self.setText(t("btn_start"))

Adding new strings:
    1. Add a new key to STRINGS (all 4 languages required).
    2. Add the same key to translations.md table.
"""

from PySide6.QtCore import QObject, Signal

# ── Supported languages ──────────────────────────────────────────────────────
LANGUAGES: dict[str, str] = {
    "ru": "RU",
    "en": "EN",
    "zh": "ZN",
    "vi": "VI",
}

# ── Translation table ─────────────────────────────────────────────────────────
# Keys are stable identifiers. Values are dicts lang → text.
# Source of truth is translations.md (generated from this dict).
STRINGS: dict[str, dict[str, str]] = {

    # ── Application ────────────────────────────────────────────────────────
    "app_title": {
        "ru": "ЭИТ — Монитор пациента",
        "en": "EIT — Patient Monitor",
        "zh": "EIT — 患者监护仪",
        "vi": "EIT — Màn hình bệnh nhân",
    },

    # ── Header bar ─────────────────────────────────────────────────────────
    "hdr_adult": {
        "ru": "👤 Взрослый",
        "en": "👤 Adult",
        "zh": "👤 成人",
        "vi": "👤 Người lớn",
    },
    "hdr_child": {
        "ru": "🧒 Ребёнок",
        "en": "🧒 Child",
        "zh": "🧒 儿童",
        "vi": "🧒 Trẻ em",
    },
    "hdr_breath_normal": {
        "ru": "ТИП ДЫХАНИЯ: НОРМАЛЬНОЕ",
        "en": "BREATHING TYPE: NORMAL",
        "zh": "呼吸类型：正常",
        "vi": "LOẠI THỞ: BÌNH THƯỜNG",
    },
    "hdr_alarm": {
        "ru": "⚠  СИГНАЛ ТРЕВОГИ",
        "en": "⚠  ALARM",
        "zh": "⚠  警报",
        "vi": "⚠  BÁO ĐỘNG",
    },
    "hdr_menu_tooltip": {
        "ru": "Главное меню",
        "en": "Main Menu",
        "zh": "主菜单",
        "vi": "Menu chính",
    },

    # ── Navigation panel ───────────────────────────────────────────────────
    "nav_main": {
        "ru": "🏠  Главное\nокно",
        "en": "🏠  Main\nwindow",
        "zh": "🏠  主\n窗口",
        "vi": "🏠  Cửa sổ\nchính",
    },
    "nav_patient": {
        "ru": "👤  Пациент",
        "en": "👤  Patient",
        "zh": "👤  患者",
        "vi": "👤  Bệnh nhân",
    },
    "nav_trends": {
        "ru": "📈  Тренды",
        "en": "📈  Trends",
        "zh": "📈  趋势",
        "vi": "📈  Xu hướng",
    },
    "nav_analysis": {
        "ru": "🔬  Анализ",
        "en": "🔬  Analysis",
        "zh": "🔬  分析",
        "vi": "🔬  Phân tích",
    },
    "nav_eit_settings": {
        "ru": "⚙  Настройки\nЭИТ",
        "en": "⚙  EIT\nSettings",
        "zh": "⚙  EIT\n设置",
        "vi": "⚙  Cài đặt\nEIT",
    },
    "nav_reports": {
        "ru": "📋  Отчёты",
        "en": "📋  Reports",
        "zh": "📋  报告",
        "vi": "📋  Báo cáo",
    },
    "nav_export": {
        "ru": "💾  Экспорт\nданных",
        "en": "💾  Export\ndata",
        "zh": "💾  导出\n数据",
        "vi": "💾  Xuất\ndữ liệu",
    },
    "nav_service": {
        "ru": "🔧  Служебная\nинформация",
        "en": "🔧  Service\ninformation",
        "zh": "🔧  服务\n信息",
        "vi": "🔧  Thông tin\ndịch vụ",
    },
    "nav_system": {
        "ru": "ℹ  Системная\nинформация",
        "en": "ℹ  System\ninformation",
        "zh": "ℹ  系统\n信息",
        "vi": "ℹ  Thông tin\nhệ thống",
    },
    "nav_debug": {
        "ru": "🛠  Отладка и\nТестирование",
        "en": "🛠  Debug &\nTesting",
        "zh": "🛠  调试与\n测试",
        "vi": "🛠  Gỡ lỗi &\nKiểm tra",
    },
    "nav_signal_quality": {
        "ru": "Качество\nсигнала ЭС",
        "en": "Signal\nquality ES",
        "zh": "信号\n质量",
        "vi": "Chất lượng\ntín hiệu",
    },

    # ── Lung visualisation ─────────────────────────────────────────────────
    "lung_breath_cycle": {
        "ru": "Дыхательный цикл",
        "en": "Breathing cycle",
        "zh": "呼吸周期",
        "vi": "Chu kỳ thở",
    },


    # ── Waveform section headers ───────────────────────────────────────────
    "wave_t_label": {
        "ru": "T  Глобальная аэрация",
        "en": "T  Global aeration",
        "zh": "T  全局通气",
        "vi": "T  Thông khí toàn thể",
    },
    "wave_r_label": {
        "ru": "R  Правое лёгкое",
        "en": "R  Right lung",
        "zh": "R  右肺",
        "vi": "R  Phổi phải",
    },
    "wave_l_label": {
        "ru": "L  Левое лёгкое",
        "en": "L  Left lung",
        "zh": "L  左肺",
        "vi": "L  Phổi trái",
    },
    "wave_rr_unit": {
        "ru": "вд/мин",
        "en": "br/min",
        "zh": "次/分",
        "vi": "lần/phút",
    },
    "wave_event_marker": {
        "ru": "⚑  МАРКЕР СОБЫТИЙ",
        "en": "⚑  EVENT MARKER",
        "zh": "⚑  事件标记",
        "vi": "⚑  ĐÁNH DẤU SỰ KIỆN",
    },
    "wave_trend": {
        "ru": "Тренд",
        "en": "Trend",
        "zh": "趋势",
        "vi": "Xu hướng",
    },

    # ── Left panel / parameters ────────────────────────────────────────────
    "param_eit_duration": {
        "ru": "Длительность ЭИТ:",
        "en": "EIT Duration:",
        "zh": "EIT持续时间:",
        "vi": "Thời gian EIT:",
    },
    "param_es_time": {
        "ru": "Время использ. ЭС:",
        "en": "ES Usage Time:",
        "zh": "ES使用时间:",
        "vi": "Thời gian sử dụng ES:",
    },
    "btn_start": {
        "ru": "▶  СТАРТ",
        "en": "▶  START",
        "zh": "▶  开始",
        "vi": "▶  BẮT ĐẦU",
    },
    "btn_stop": {
        "ru": "⏹  СТОП",
        "en": "⏹  STOP",
        "zh": "⏹  停止",
        "vi": "⏹  DỪNG",
    },

    # ── Patient screen ────────────────────────────────────────────────────
    "pat_card_title": {
        "ru": "Карточка пациента",
        "en": "Patient card",
        "zh": "患者卡",
        "vi": "Thẻ bệnh nhân",
    },
    "pat_last_name": {
        "ru": "Фамилия",
        "en": "Last name",
        "zh": "姓",
        "vi": "Họ",
    },
    "pat_first_name": {
        "ru": "Имя",
        "en": "First name",
        "zh": "名",
        "vi": "Tên",
    },
    "pat_patronymic": {
        "ru": "Отчество",
        "en": "Patronymic",
        "zh": "父名",
        "vi": "Tên đệm",
    },
    "pat_dob": {
        "ru": "Дата рождения",
        "en": "Date of birth",
        "zh": "出生日期",
        "vi": "Ngày sinh",
    },
    "pat_gender": {
        "ru": "Пол",
        "en": "Gender",
        "zh": "性别",
        "vi": "Giới tính",
    },
    "pat_gender_m": {
        "ru": "Мужской",
        "en": "Male",
        "zh": "男",
        "vi": "Nam",
    },
    "pat_gender_f": {
        "ru": "Женский",
        "en": "Female",
        "zh": "女",
        "vi": "Nữ",
    },
    "pat_record_num": {
        "ru": "Номер истории болезни",
        "en": "Medical record №",
        "zh": "病历号",
        "vi": "Số hồ sơ bệnh án",
    },
    "pat_weight": {
        "ru": "Вес, кг",
        "en": "Weight, kg",
        "zh": "体重 (千克)",
        "vi": "Cân nặng (kg)",
    },
    "pat_height": {
        "ru": "Рост, см",
        "en": "Height, cm",
        "zh": "身高 (厘米)",
        "vi": "Chiều cao (cm)",
    },
    "pat_id": {
        "ru": "ID",
        "en": "ID",
        "zh": "ID",
        "vi": "ID",
    },
    "pat_chest": {
        "ru": "Охват грудной клетки, см",
        "en": "Chest circumference, cm",
        "zh": "胸围 (厘米)",
        "vi": "Vòng ngực (cm)",
    },
    "pat_age": {
        "ru": "Полных лет",
        "en": "Age (full years)",
        "zh": "周岁",
        "vi": "Tuổi (tròn)",
    },
    "pat_assign_id": {
        "ru": "Присвоить код ID",
        "en": "Assign ID code",
        "zh": "分配ID代码",
        "vi": "Gán mã ID",
    },
    "pat_personal_title": {
        "ru": "Персонализация",
        "en": "Personalization",
        "zh": "个性化",
        "vi": "Cá nhân hóa",
    },
    "pat_lung_morph": {
        "ru": "Морфология лёгких\n(определить границы)",
        "en": "Lung morphology\n(define boundaries)",
        "zh": "肺形态学\n(确定边界)",
        "vi": "Hình thái phổi\n(xác định ranh giới)",
    },
    "pat_load_dicom": {
        "ru": "Загрузить снимок DICOM",
        "en": "Load DICOM image",
        "zh": "加载DICOM图像",
        "vi": "Tải ảnh DICOM",
    },
    "pat_preview": {
        "ru": "Предварительный\nпросмотр",
        "en": "Preview",
        "zh": "预览",
        "vi": "Xem trước",
    },
    "pat_clinical_title": {
        "ru": "Клинические данные",
        "en": "Clinical data",
        "zh": "临床数据",
        "vi": "Dữ liệu lâm sàng",
    },
    "pat_main_diag": {
        "ru": "Диагноз основной",
        "en": "Main diagnosis",
        "zh": "主要诊断",
        "vi": "Chẩn đoán chính",
    },
    "pat_accompany_diag": {
        "ru": "Диагноз сопутствующий",
        "en": "Accompanying diagnosis",
        "zh": "伴随诊断",
        "vi": "Chẩn đoán kèm theo",
    },
    "pat_icd_code": {
        "ru": "МКБ-11",
        "en": "ICD-11",
        "zh": "ICD-11",
        "vi": "ICD-11",
    },
    "pat_ivl": {
        "ru": "ИВЛ",
        "en": "Mechanical ventilation",
        "zh": "机械通气",
        "vi": "Thở máy",
    },
    "pat_yes": {
        "ru": "Да",
        "en": "Yes",
        "zh": "是",
        "vi": "Có",
    },
    "pat_no": {
        "ru": "Нет",
        "en": "No",
        "zh": "否",
        "vi": "Không",
    },
    "pat_details": {
        "ru": "Подробнее",
        "en": "Details",
        "zh": "详情",
        "vi": "Chi tiết",
    },
    "pat_history_title": {
        "ru": "История исследований",
        "en": "Study history",
        "zh": "检查历史",
        "vi": "Lịch sử nghiên cứu",
    },
    "pat_prev_study": {
        "ru": "Предыдущее исследование ЭИТ",
        "en": "Previous EIT study",
        "zh": "上次EIT检查",
        "vi": "Nghiên cứu EIT trước",
    },
    "pat_save_card": {
        "ru": "Сохранить карточку",
        "en": "Save card",
        "zh": "保存档案",
        "vi": "Lưu hồ sơ",
    },
    "pat_link_study": {
        "ru": "Привязать текущее исследование\nк выбранному пациенту",
        "en": "Link current study\nto selected patient",
        "zh": "将当前检查与\n所选患者关联",
        "vi": "Liên kết nghiên cứu hiện tại\nvới bệnh nhân đã chọn",
    },

    # ── Screen titles ──────────────────────────────────────────────────────
    "screen_main": {
        "ru": "ГЛАВНОЕ ОКНО",
        "en": "MAIN WINDOW",
        "zh": "主窗口",
        "vi": "CỬA SỔ CHÍNH",
    },
    "screen_patient": {
        "ru": "ПАЦИЕНТ",
        "en": "PATIENT",
        "zh": "患者",
        "vi": "BỆNH NHÂN",
    },
    "screen_analysis": {
        "ru": "АНАЛИЗ",
        "en": "ANALYSIS",
        "zh": "分析",
        "vi": "PHÂN TÍCH",
    },
    "screen_trends": {
        "ru": "ТРЕНДЫ",
        "en": "TRENDS",
        "zh": "趋势",
        "vi": "XU HƯỚNG",
    },
    "screen_eit_settings": {
        "ru": "НАСТРОЙКИ ЭИТ",
        "en": "EIT SETTINGS",
        "zh": "EIT设置",
        "vi": "CÀI ĐẶT EIT",
    },
    "screen_service": {
        "ru": "СЛУЖЕБНАЯ ИНФОРМАЦИЯ",
        "en": "SERVICE INFORMATION",
        "zh": "服务信息",
        "vi": "THÔNG TIN DỊCH VỤ",
    },
    "screen_system": {
        "ru": "СИСТЕМНАЯ ИНФОРМАЦИЯ",
        "en": "SYSTEM INFORMATION",
        "zh": "系统信息",
        "vi": "THÔNG TIN HỆ THỐNG",
    },
    "screen_export": {
        "ru": "ЭКСПОРТ ДАННЫХ",
        "en": "EXPORT DATA",
        "zh": "导出数据",
        "vi": "XUẤT DỮ LIỆU",
    },
    "screen_reports": {
        "ru": "ОТЧЁТЫ",
        "en": "REPORTS",
        "zh": "报告",
        "vi": "BÁO CÁO",
    },
    "screen_debug": {
        "ru": "ОТЛАДКА И ТЕСТИРОВАНИЕ",
        "en": "DEBUG AND TESTING",
        "zh": "调试与测试",
        "vi": "GỠ LỖI VÀ KIỂM TRA",
    },

    # ── Screen subtitles (stubs) ───────────────────────────────────────────
    "sub_in_development": {
        "ru": "В разработке",
        "en": "In development",
        "zh": "开发中",
        "vi": "Đang phát triển",
    },
    "sub_patient": {
        "ru": "Ввод и редактирование данных пациента",
        "en": "Enter and edit patient data",
        "zh": "输入和编辑患者数据",
        "vi": "Nhập và chỉnh sửa dữ liệu bệnh nhân",
    },
    "sub_analysis": {
        "ru": "Детальный анализ параметров вентиляции",
        "en": "Detailed ventilation parameter analysis",
        "zh": "详细通气参数分析",
        "vi": "Phân tích chi tiết các thông số thông khí",
    },
    "sub_trends": {
        "ru": "Тренды глобальной и регионарной аэрации лёгких",
        "en": "Global and regional lung aeration trends",
        "zh": "全局和区域肺通气趋势",
        "vi": "Xu hướng thông khí phổi toàn thể và khu vực",
    },
    "sub_eit_settings": {
        "ru": "Конфигурация параметров электроимпедансной томографии",
        "en": "Electrical impedance tomography configuration",
        "zh": "电阻抗断层扫描配置",
        "vi": "Cấu hình chụp cắt lớp điện trở",
    },
    "sub_service": {
        "ru": "Протоколирование неблагоприятных событий",
        "en": "Adverse event logging",
        "zh": "不良事件记录",
        "vi": "Ghi nhật ký sự kiện bất lợi",
    },
    "sub_export": {
        "ru": "Экспорт данных мониторинга в внешние форматы",
        "en": "Export monitoring data to external formats",
        "zh": "将监测数据导出为外部格式",
        "vi": "Xuất dữ liệu giám sát sang định dạng ngoài",
    },
    "sub_reports": {
        "ru": "Формирование и просмотр клинических отчётов",
        "en": "Generate and view clinical reports",
        "zh": "生成和查看临床报告",
        "vi": "Tạo và xem báo cáo lâm sàng",
    },
    "sub_debug": {
        "ru": "Инструменты диагностики и тестирования системы",
        "en": "System diagnostics and testing tools",
        "zh": "系统诊断和测试工具",
        "vi": "Công cụ chẩn đoán và kiểm tra hệ thống",
    },

    # ── Trends screen ─────────────────────────────────────────────────────
    "trends_tab_global": {
        "ru": "Тренд ГЛОБАЛЬНОЙ аэрации",
        "en": "GLOBAL Aeration Trend",
        "zh": "全局通气趋势",
        "vi": "Xu hướng thông khí TOÀN THỂ",
    },
    "trends_tab_regional": {
        "ru": "Тренд РЕГИОНАРНОЙ аэрации",
        "en": "REGIONAL Aeration Trend",
        "zh": "区域通气趋势",
        "vi": "Xu hướng thông khí KHU VỰC",
    },
    "trends_tab_all": {
        "ru": "Все тренды АЭРАЦИИ",
        "en": "All Aeration Trends",
        "zh": "所有通气趋势",
        "vi": "Tất cả xu hướng thông khí",
    },
    "trends_dz": {
        "ru": "ΔZ,%",
        "en": "ΔZ,%",
        "zh": "ΔZ,%",
        "vi": "ΔZ,%",
    },
    "trends_trend": {
        "ru": "Тренд",
        "en": "Trend",
        "zh": "趋势",
        "vi": "Xu hướng",
    },
    "trends_table": {
        "ru": "Таблица",
        "en": "Table",
        "zh": "表格",
        "vi": "Bảng",
    },
    "trends_time_hours": {
        "ru": "Время, часы",
        "en": "Time, hours",
        "zh": "时间（小时）",
        "vi": "Thời gian, giờ",
    },
    "trends_time_min": {
        "ru": "Время, минуты",
        "en": "Time, minutes",
        "zh": "时间（分钟）",
        "vi": "Thời gian, phút",
    },
    "trends_btn_scale": {
        "ru": "Масштаб",
        "en": "Scale",
        "zh": "缩放",
        "vi": "Tỉ lệ",
    },
    "trends_btn_express": {
        "ru": "Экспресс-мониторинг",
        "en": "Express monitoring",
        "zh": "快速监测",
        "vi": "Giám sát nhanh",
    },
    "trends_btn_marker": {
        "ru": "Маркер событий",
        "en": "Event marker",
        "zh": "事件标记",
        "vi": "Đánh dấu sự kiện",
    },
    "trends_btn_exit": {
        "ru": "Выход",
        "en": "Exit",
        "zh": "退出",
        "vi": "Thoát",
    },
    "trends_right_short": {
        "ru": "Правое лёгкое (R)",
        "en": "Right lung (R)",
        "zh": "右肺 (R)",
        "vi": "Phổi phải (R)",
    },
    "trends_left_short": {
        "ru": "Левое лёгкое (L)",
        "en": "Left lung (L)",
        "zh": "左肺 (L)",
        "vi": "Phổi trái (L)",
    },
    "trends_global_label": {
        "ru": "GLOBAL",
        "en": "GLOBAL",
        "zh": "全局",
        "vi": "TOÀN THỂ",
    },
    "trends_reg_label": {
        "ru": "REG",
        "en": "REG",
        "zh": "区域",
        "vi": "KHU VỰC",
    },

    # ── System info screen ─────────────────────────────────────────────────
    "sys_lang_section": {
        "ru": "Язык интерфейса",
        "en": "Interface language",
        "zh": "界面语言",
        "vi": "Ngôn ngữ giao diện",
    },
    "sys_lang_current": {
        "ru": "Текущий язык:",
        "en": "Current language:",
        "zh": "当前语言:",
        "vi": "Ngôn ngữ hiện tại:",
    },
    "sys_lang_change_btn": {
        "ru": "Изменить язык",
        "en": "Change language",
        "zh": "更改语言",
        "vi": "Thay đổi ngôn ngữ",
    },
    "sys_version": {
        "ru": "Версия ПО:",
        "en": "Software version:",
        "zh": "软件版本:",
        "vi": "Phiên bản phần mềm:",
    },
    "sys_device_id": {
        "ru": "ID устройства:",
        "en": "Device ID:",
        "zh": "设备ID:",
        "vi": "ID thiết bị:",
    },

    # Table 7.5 row labels
    "sys_lbl_sw_name": {
        "ru": "Наименование ПО",
        "en": "Software name",
        "zh": "软件名称",
        "vi": "Tên phần mềm",
    },
    "sys_lbl_version": {
        "ru": "Версия ПО",
        "en": "Software version",
        "zh": "软件版本",
        "vi": "Phiên bản phần mềm",
    },
    "sys_lbl_release_date": {
        "ru": "Дата выпуска",
        "en": "Release date",
        "zh": "发布日期",
        "vi": "Ngày phát hành",
    },
    "sys_lbl_serial": {
        "ru": "Серийный номер",
        "en": "Serial number",
        "zh": "序列号",
        "vi": "Số sê-ri",
    },
    "sys_lbl_device_model": {
        "ru": "Модель устройства ЭИТ",
        "en": "EIT device model",
        "zh": "EIT设备型号",
        "vi": "Mô hình thiết bị EIT",
    },
    "sys_lbl_electrodes": {
        "ru": "Количество электродов",
        "en": "Number of electrodes",
        "zh": "电极数量",
        "vi": "Số điện cực",
    },
    "sys_lbl_belts": {
        "ru": "Количество электродных поясов",
        "en": "Number of electrode belts",
        "zh": "电极带数",
        "vi": "Số vòng điện cực",
    },
    "sys_lbl_freq": {
        "ru": "Частота инжектируемого тока",
        "en": "Injected current frequency",
        "zh": "注入电流频率",
        "vi": "Tần số dòng tiêm",
    },
    "sys_lbl_current": {
        "ru": "Сила инжектируемого тока",
        "en": "Injected current amplitude",
        "zh": "注入电流强度",
        "vi": "Cường độ dòng tiêm",
    },
    "sys_lbl_battery": {
        "ru": "Заряд АКБ",
        "en": "Battery charge",
        "zh": "电池电量",
        "vi": "Mức pin",
    },
    "sys_lbl_datetime": {
        "ru": "Дата и время",
        "en": "Date and time",
        "zh": "日期和时间",
        "vi": "Ngày và giờ",
    },
    "sys_lbl_language": {
        "ru": "Язык интерфейса",
        "en": "Interface language",
        "zh": "界面语言",
        "vi": "Ngôn ngữ giao diện",
    },

    # Table 7.5 translated values
    "sys_val_sw_name": {
        "ru": "Прототип системы ЭИТ",
        "en": "EIT System Prototype",
        "zh": "EIT系统原型",
        "vi": "Nguyên mẫu hệ thống EIT",
    },
    "sys_val_freq": {
        "ru": "от 10 до 500 кГц ± 10%",
        "en": "10 to 500 kHz ± 10%",
        "zh": "10至500 kHz ± 10%",
        "vi": "10 đến 500 kHz ± 10%",
    },
    "sys_val_current": {
        "ru": "0,5 до 5 мА ± 10%",
        "en": "0.5 to 5 mA ± 10%",
        "zh": "0.5至5 mA ± 10%",
        "vi": "0,5 đến 5 mA ± 10%",
    },

    # Table column headers
    "sys_tbl_num": {
        "ru": "№ п/п",
        "en": "#",
        "zh": "序号",
        "vi": "STT",
    },
    "sys_tbl_param": {
        "ru": "Параметр",
        "en": "Parameter",
        "zh": "参数",
        "vi": "Thông số",
    },
    "sys_tbl_value": {
        "ru": "Формат данных",
        "en": "Data format",
        "zh": "数据格式",
        "vi": "Định dạng dữ liệu",
    },

    # ── Signal quality screen ──────────────────────────────────────────────
    "sq_lbl_monitor_duration": {
        "ru": "Длительность мониторинга",
        "en": "Monitoring duration",
        "zh": "监测持续时间",
        "vi": "Thời gian giám sát",
    },
    "sq_lbl_es_duration": {
        "ru": "Длительность использования ЭС",
        "en": "Electrode system usage time",
        "zh": "电极系统使用时间",
        "vi": "Thời gian sử dụng hệ điện cực",
    },
    "sq_btn_calibrate": {
        "ru": "Калибровка",
        "en": "Calibrate",
        "zh": "校准",
        "vi": "Hiệu chỉnh",
    },
    "sq_quality_tech_error": {
        "ru": "Техническая ошибка",
        "en": "Technical error",
        "zh": "技术故障",
        "vi": "Lỗi kỹ thuật",
    },
    "sq_quality_insufficient": {
        "ru": "Недостаточно",
        "en": "Insufficient",
        "zh": "不足",
        "vi": "Không đủ",
    },
    "sq_quality_weak": {
        "ru": "Слабый",
        "en": "Weak",
        "zh": "弱",
        "vi": "Yếu",
    },
    "sq_quality_adequate": {
        "ru": "Адекватный",
        "en": "Adequate",
        "zh": "适中",
        "vi": "Phù hợp",
    },
    "sq_quality_strong": {
        "ru": "Сильный",
        "en": "Strong",
        "zh": "强",
        "vi": "Mạnh",
    },

    # ── EIT settings screen ────────────────────────────────────────────────
    "eit_current_label": {
        "ru": "Сила инжектируемого тока",
        "en": "Injected current amplitude",
        "zh": "注入电流强度",
        "vi": "Cường độ dòng tiêm",
    },
    "eit_current_placeholder": {
        "ru": "Сила тока",
        "en": "Current",
        "zh": "电流",
        "vi": "Dòng điện",
    },
    "eit_freq_label": {
        "ru": "Частота инжектируемого тока",
        "en": "Injected current frequency",
        "zh": "注入电流频率",
        "vi": "Tần số dòng tiêm",
    },
    "eit_freq_placeholder": {
        "ru": "Частота",
        "en": "Frequency",
        "zh": "频率",
        "vi": "Tần số",
    },
    "eit_electrodes_label": {
        "ru": "Количество электродов",
        "en": "Number of electrodes",
        "zh": "电极数量",
        "vi": "Số điện cực",
    },
    "eit_belts_label": {
        "ru": "Количество электродных поясов",
        "en": "Number of electrode belts",
        "zh": "电极带数",
        "vi": "Số vòng điện cực",
    },
    "eit_unit_ma": {
        "ru": "мА",
        "en": "mA",
        "zh": "毫安",
        "vi": "mA",
    },
    "eit_unit_khz": {
        "ru": "кГц",
        "en": "kHz",
        "zh": "千赫",
        "vi": "kHz",
    },
    "eit_unit_pcs": {
        "ru": "шт",
        "en": "pcs",
        "zh": "个",
        "vi": "cái",
    },
    "eit_viz_color_label": {
        "ru": "Задание цвета динамической\nвизуализации дыхательного цикла",
        "en": "Colour mode of breathing\ncycle dynamic visualisation",
        "zh": "呼吸周期动态\n可视化颜色设置",
        "vi": "Màu sắc hình ảnh động\ncủa chu kỳ thở",
    },
    "eit_viz_2colors": {
        "ru": "2 цвета",
        "en": "2 colours",
        "zh": "2色",
        "vi": "2 màu",
    },
    "eit_viz_standard": {
        "ru": "Стандартное",
        "en": "Standard",
        "zh": "标准",
        "vi": "Tiêu chuẩn",
    },
    "eit_pathology_label": {
        "ru": "Идентификация и отображение типа\nпатологического дыхания",
        "en": "Identification and display of\npathological breathing type",
        "zh": "病理呼吸类型\n识别与显示",
        "vi": "Nhận dạng và hiển thị\nloại thở bệnh lý",
    },
    "eit_btn_save": {
        "ru": "Сохранить настройки\nЭИТ-исследования",
        "en": "Save EIT study\nsettings",
        "zh": "保存EIT研究\n设置",
        "vi": "Lưu cài đặt\nnghiên cứu EIT",
    },
    "eit_btn_reset": {
        "ru": "Сбросить настройки",
        "en": "Reset settings",
        "zh": "重置设置",
        "vi": "Đặt lại cài đặt",
    },

    # ── Export data screen ─────────────────────────────────────────────────
    "exp_format_title": {
        "ru": "Формат экспорта",
        "en": "Export format",
        "zh": "导出格式",
        "vi": "Định dạng xuất",
    },
    "exp_history_title": {
        "ru": "История исследований",
        "en": "Study history",
        "zh": "检查历史",
        "vi": "Lịch sử nghiên cứu",
    },
    "exp_prev_study": {
        "ru": "Предыдущее исследование ЭИТ",
        "en": "Previous EIT study",
        "zh": "上次EIT检查",
        "vi": "Nghiên cứu EIT trước",
    },
    "exp_btn_details": {
        "ru": "Подробнее",
        "en": "Details",
        "zh": "详情",
        "vi": "Chi tiết",
    },
    "exp_btn_reset": {
        "ru": "Сбросить настройки",
        "en": "Reset settings",
        "zh": "重置设置",
        "vi": "Đặt lại cài đặt",
    },
    "exp_btn_generate": {
        "ru": "Сформировать",
        "en": "Generate",
        "zh": "生成",
        "vi": "Tạo",
    },

    # ── Analysis screen ───────────────────────────────────────────────────────
    "analysis_tab_pathology": {
        "ru": "Тип патологического дыхания",
        "en": "Pathological Breathing Type",
        "zh": "病理呼吸类型",
        "vi": "Loại thở bệnh lý",
    },
    "analysis_tab_global": {
        "ru": "Аэрация\nГЛОБАЛЬНАЯ",
        "en": "GLOBAL\nAeration",
        "zh": "全局\n通气",
        "vi": "Thông khí\nTOÀN THỂ",
    },
    "analysis_tab_regional": {
        "ru": "Аэрация\nРЕГИОНАРНАЯ",
        "en": "REGIONAL\nAeration",
        "zh": "区域\n通气",
        "vi": "Thông khí\nKHU VỰC",
    },
    "analysis_sub_pca": {
        "ru": "Анализ PCA",
        "en": "PCA Analysis",
        "zh": "PCA分析",
        "vi": "Phân tích PCA",
    },
    "analysis_sub_avg": {
        "ru": "Усредн. графики аэрации",
        "en": "Averaged aeration charts",
        "zh": "平均通气图",
        "vi": "Biểu đồ thông khí TB",
    },
    "analysis_possible_types": {
        "ru": "Возможные типы дыхания",
        "en": "Possible breathing types",
        "zh": "可能的呼吸类型",
        "vi": "Các loại thở có thể",
    },
    "analysis_current_type": {
        "ru": "Текущий тип дыхания",
        "en": "Current breathing type",
        "zh": "当前呼吸类型",
        "vi": "Loại thở hiện tại",
    },
    "analysis_bt_eupnea":            {"ru": "Эупноэ",                   "en": "Eupnea",               "zh": "正常呼吸",       "vi": "Thở bình thường"},
    "analysis_bt_periodic":          {"ru": "Периодическое дыхание",    "en": "Periodic breathing",   "zh": "周期性呼吸",     "vi": "Thở tuần hoàn"},
    "analysis_bt_tachypnea":         {"ru": "Тахипноэ",                 "en": "Tachypnea",            "zh": "呼吸急促",       "vi": "Thở nhanh"},
    "analysis_bt_retraction":        {"ru": "Дыхание с ретракцией",     "en": "Retractive breathing", "zh": "回缩性呼吸",     "vi": "Thở có co rút"},
    "analysis_bt_gasping":           {"ru": "Гаспинг",                  "en": "Gasping",              "zh": "喘息",           "vi": "Thở hổn hển"},
    "analysis_bt_bradypnea":         {"ru": "Брадипноэ",                "en": "Bradypnea",            "zh": "呼吸缓慢",       "vi": "Thở chậm"},
    "analysis_bt_dyspnea":           {"ru": "Диспноэ",                  "en": "Dyspnea",              "zh": "呼吸困难",       "vi": "Khó thở"},
    "analysis_bt_apnea_central":     {"ru": "Апноэ центральное",        "en": "Central apnea",        "zh": "中枢性呼吸暂停", "vi": "Ngừng thở trung ương"},
    "analysis_bt_apnea_obstructive": {"ru": "Апноэ обструктивное",      "en": "Obstructive apnea",    "zh": "阻塞性呼吸暂停", "vi": "Ngừng thở tắc nghẽn"},
    "analysis_bt_apnea_mixed":       {"ru": "Апноэ смешанное",          "en": "Mixed apnea",          "zh": "混合性呼吸暂停", "vi": "Ngừng thở hỗn hợp"},
    "analysis_bt_apnea_reflex":      {"ru": "Апноэ рефлекторное",       "en": "Reflex apnea",         "zh": "反射性呼吸暂停", "vi": "Ngừng thở phản xạ"},
    # legacy keys kept for compatibility
    "analysis_bt_apnea":       {"ru": "Апноэ",                      "en": "Apnea",                "zh": "呼吸暂停",   "vi": "Ngừng thở"},
    "analysis_bt_apneustic":   {"ru": "Апнейстическое",             "en": "Apneustic",            "zh": "长吸气式",   "vi": "Thở ngưng mạnh"},
    "analysis_bt_biot":        {"ru": "Биота",                      "en": "Biot's",               "zh": "比奥式",     "vi": "Thở Biot"},
    "analysis_bt_cheyne":      {"ru": "Чейна-Стокса",               "en": "Cheyne-Stokes",        "zh": "陈-施式",    "vi": "Cheyne-Stokes"},
    "analysis_bt_restrictive": {"ru": "Дыхание с рестрикцией",      "en": "Restrictive breathing","zh": "限制性呼吸", "vi": "Thở hạn chế"},

    # ── Reports screen ────────────────────────────────────────────────────────
    "rep_saved_reports": {
        "ru": "Сохранённые отчёты",
        "en": "Saved reports",
        "zh": "已保存报告",
        "vi": "Báo cáo đã lưu",
    },
    "rep_create_new": {
        "ru": "Сформировать новый отчёт",
        "en": "Create new report",
        "zh": "创建新报告",
        "vi": "Tạo báo cáo mới",
    },
    "rep_period": {
        "ru": "Период",
        "en": "Period",
        "zh": "时间段",
        "vi": "Khoảng thời gian",
    },
    "rep_period_from": {
        "ru": "С",
        "en": "From",
        "zh": "从",
        "vi": "Từ",
    },
    "rep_period_to": {
        "ru": "По",
        "en": "To",
        "zh": "至",
        "vi": "Đến",
    },
    "rep_patient": {
        "ru": "Пациент",
        "en": "Patient",
        "zh": "患者",
        "vi": "Bệnh nhân",
    },
    "rep_indicators": {
        "ru": "Набор показателей",
        "en": "Indicator set",
        "zh": "指标集",
        "vi": "Bộ chỉ số",
    },
    "rep_report_name": {
        "ru": "Наименование отчёта",
        "en": "Report name",
        "zh": "报告名称",
        "vi": "Tên báo cáo",
    },
    "rep_btn_view": {
        "ru": "Просмотр",
        "en": "View",
        "zh": "查看",
        "vi": "Xem",
    },
    "rep_btn_print": {
        "ru": "Печать",
        "en": "Print",
        "zh": "打印",
        "vi": "In",
    },
    "rep_btn_generate": {
        "ru": "Сформировать отчёт",
        "en": "Generate report",
        "zh": "生成报告",
        "vi": "Tạo báo cáo",
    },
    "rep_btn_reset": {
        "ru": "Сбросить параметры",
        "en": "Reset parameters",
        "zh": "重置参数",
        "vi": "Đặt lại thông số",
    },
    "rep_preview_title": {
        "ru": "Предварительный просмотр",
        "en": "Preview",
        "zh": "预览",
        "vi": "Xem trước",
    },
    "rep_preview_empty": {
        "ru": "Выберите отчёт из списка\nили сформируйте новый",
        "en": "Select a report from the list\nor create a new one",
        "zh": "从列表中选择报告\n或创建新报告",
        "vi": "Chọn báo cáo từ danh sách\nhoặc tạo báo cáo mới",
    },
    "rep_new_btn": {
        "ru": "+ Новый отчёт",
        "en": "+ New report",
        "zh": "+ 新报告",
        "vi": "+ Báo cáo mới",
    },
    "rep_conclusion": {
        "ru": "ЗАКЛЮЧЕНИЕ",
        "en": "CONCLUSION",
        "zh": "结论",
        "vi": "KẾT LUẬN",
    },
    "rep_indicators_section": {
        "ru": "ПОКАЗАТЕЛИ ВЕНТИЛЯЦИИ",
        "en": "VENTILATION INDICATORS",
        "zh": "通气指标",
        "vi": "CHỈ SỐ THÔNG KHÍ",
    },
    "rep_eit_study": {
        "ru": "Исследование ЭИТ",
        "en": "EIT Study",
        "zh": "EIT检查",
        "vi": "Nghiên cứu EIT",
    },

    # ── Service info screen ───────────────────────────────────────────────────
    "svc_filter_type": {
        "ru": "Фильтр по типу:",
        "en": "Filter by type:",
        "zh": "按类型筛选:",
        "vi": "Lọc theo loại:",
    },
    "svc_filter_all": {
        "ru": "Все типы",
        "en": "All types",
        "zh": "所有类型",
        "vi": "Tất cả loại",
    },
    "svc_btn_reset_filter": {
        "ru": "Сбросить",
        "en": "Reset",
        "zh": "重置",
        "vi": "Đặt lại",
    },
    "svc_btn_add": {
        "ru": "+ Добавить событие",
        "en": "+ Add event",
        "zh": "+ 添加事件",
        "vi": "+ Thêm sự kiện",
    },
    "svc_col_num": {
        "ru": "№",
        "en": "#",
        "zh": "序",
        "vi": "STT",
    },
    "svc_col_datetime": {
        "ru": "Дата / Время",
        "en": "Date / Time",
        "zh": "日期 / 时间",
        "vi": "Ngày / Giờ",
    },
    "svc_col_type": {
        "ru": "Тип",
        "en": "Type",
        "zh": "类型",
        "vi": "Loại",
    },
    "svc_col_desc": {
        "ru": "Описание",
        "en": "Description",
        "zh": "描述",
        "vi": "Mô tả",
    },
    "svc_no_events": {
        "ru": "Нет зарегистрированных событий",
        "en": "No events recorded",
        "zh": "暂无记录事件",
        "vi": "Không có sự kiện nào",
    },
    # Event type labels
    "svc_type_tech_error": {
        "ru": "Техническая ошибка",
        "en": "Technical error",
        "zh": "技术故障",
        "vi": "Lỗi kỹ thuật",
    },
    "svc_type_adverse_event": {
        "ru": "Неблагоприятное событие",
        "en": "Adverse event",
        "zh": "不良事件",
        "vi": "Sự kiện bất lợi",
    },
    "svc_type_adverse_phenom": {
        "ru": "Неблагоприятное явление",
        "en": "Adverse phenomenon",
        "zh": "不良现象",
        "vi": "Hiện tượng bất lợi",
    },
    "svc_type_operator_note": {
        "ru": "Замечание оператора",
        "en": "Operator note",
        "zh": "操作员备注",
        "vi": "Ghi chú của thao tác viên",
    },
    # Add event dialog
    "svc_dlg_title": {
        "ru": "Добавить событие",
        "en": "Add event",
        "zh": "添加事件",
        "vi": "Thêm sự kiện",
    },
    "svc_dlg_datetime": {
        "ru": "Дата и время:",
        "en": "Date and time:",
        "zh": "日期和时间:",
        "vi": "Ngày và giờ:",
    },
    "svc_dlg_type": {
        "ru": "Тип события:",
        "en": "Event type:",
        "zh": "事件类型:",
        "vi": "Loại sự kiện:",
    },
    "svc_dlg_desc": {
        "ru": "Описание:",
        "en": "Description:",
        "zh": "描述:",
        "vi": "Mô tả:",
    },
    "svc_dlg_desc_hint": {
        "ru": "Введите описание события...",
        "en": "Enter event description...",
        "zh": "请输入事件描述...",
        "vi": "Nhập mô tả sự kiện...",
    },
    "svc_dlg_save": {
        "ru": "Сохранить",
        "en": "Save",
        "zh": "保存",
        "vi": "Lưu",
    },
    "svc_dlg_cancel": {
        "ru": "Отмена",
        "en": "Cancel",
        "zh": "取消",
        "vi": "Hủy",
    },
    "svc_session_label": {
        "ru": "Протокол событий текущего сеанса",
        "en": "Current session event log",
        "zh": "当前会话事件记录",
        "vi": "Nhật ký sự kiện phiên hiện tại",
    },

    # ── Language selector dialog ────────────────────────────────────────────
    "dlg_lang_title": {
        "ru": "Выбор языка интерфейса",
        "en": "Select interface language",
        "zh": "选择界面语言",
        "vi": "Chọn ngôn ngữ giao diện",
    },
    "dlg_lang_confirm": {
        "ru": "Применить",
        "en": "Apply",
        "zh": "应用",
        "vi": "Áp dụng",
    },
    "dlg_lang_cancel": {
        "ru": "Отмена",
        "en": "Cancel",
        "zh": "取消",
        "vi": "Hủy",
    },
}


# ── I18n singleton ────────────────────────────────────────────────────────────

class _I18n(QObject):
    language_changed = Signal(str)   # emits new language code ("ru", "en", …)

    def __init__(self):
        super().__init__()
        self._lang = "ru"

    @property
    def lang(self) -> str:
        return self._lang

    def set_language(self, lang: str):
        if lang in LANGUAGES and lang != self._lang:
            self._lang = lang
            self.language_changed.emit(lang)

    def t(self, key: str) -> str:
        entry = STRINGS.get(key)
        if entry is None:
            return f"[{key}]"
        return entry.get(self._lang) or entry.get("ru") or f"[{key}]"


# Module-level singleton — import and use directly
i18n = _I18n()


def t(key: str) -> str:
    """Shorthand: return translated string for current language."""
    return i18n.t(key)
