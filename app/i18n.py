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
    "hdr_live": {
        "ru": "ЭФИР",
        "en": "LIVE",
        "zh": "实时",
        "vi": "TRỰC TIẾP",
    },
    "hdr_playback": {
        "ru": "АРХИВ",
        "en": "REPLAY",
        "zh": "回放",
        "vi": "PHÁT LẠI",
    },
    "pat_playback": {
        "ru": "Просмотр",
        "en": "Playback",
        "zh": "回放",
        "vi": "Phát lại",
    },
    "pat_import_eit_json": {
        "ru": "Загрузить измерения ЭИТ из JSON",
        "en": "Load EIT measurements from JSON",
        "zh": "从 JSON 加载 EIT 测量",
        "vi": "Tải phép đo EIT từ JSON",
    },
    "pat_import_eit_json_hint": {
        "ru": "Исследовательская FEM/GREIT-реконструкция; порядок каналов и геометрия требуют подтверждения",
        "en": "Research FEM/GREIT reconstruction; channel order and geometry require confirmation",
        "zh": "研究性 FEM/GREIT 重建；通道顺序和几何形状需要确认",
        "vi": "Tái tạo FEM/GREIT nghiên cứu; thứ tự kênh và hình học cần được xác nhận",
    },
    "pat_import_eit_json_filter": {
        "ru": "Измерения ЭИТ JSON (*.json)",
        "en": "EIT JSON measurements (*.json)",
        "zh": "EIT JSON 测量 (*.json)",
        "vi": "Phép đo EIT JSON (*.json)",
    },
    "pat_import_eit_json_error": {
        "ru": "Файл не удалось проверить или реконструировать. Требуются последовательные кадры по 208 числовых каналов.",
        "en": "The file could not be validated or reconstructed. Sequential frames with 208 numeric channels are required.",
        "zh": "无法验证或重建文件。需要包含 208 个数值通道的连续帧。",
        "vi": "Không thể xác thực hoặc tái tạo tệp. Cần các khung liên tiếp với 208 kênh số.",
    },
    "study_playback_unavailable": {
        "ru": "Запись исследования недоступна или повреждена.",
        "en": "The study recording is unavailable or damaged.",
        "zh": "检查记录不可用或已损坏。",
        "vi": "Bản ghi nghiên cứu không khả dụng hoặc bị hỏng.",
    },
    "playback_read_only": {
        "ru": "АРХИВ · только просмотр",
        "en": "ARCHIVE · read only",
        "zh": "存档 · 只读",
        "vi": "LƯU TRỮ · chỉ đọc",
    },
    "playback_pause": {
        "ru": "Пауза",
        "en": "Pause",
        "zh": "暂停",
        "vi": "Tạm dừng",
    },
    "playback_resume": {
        "ru": "Продолжить",
        "en": "Resume",
        "zh": "继续",
        "vi": "Tiếp tục",
    },
    "playback_close": {
        "ru": "Закрыть",
        "en": "Close",
        "zh": "关闭",
        "vi": "Đóng",
    },
    "monitor_quality_valid": {
        "ru": "Данные: качество в норме", "en": "Data quality: valid",
        "zh": "数据质量：正常", "vi": "Chất lượng dữ liệu: hợp lệ",
    },
    "monitor_quality_degraded": {
        "ru": "Данные: низкое качество", "en": "Data quality: degraded",
        "zh": "数据质量：较低", "vi": "Chất lượng dữ liệu: suy giảm",
    },
    "monitor_reason_reconstruction_hypothesis": {
        "ru": "FEM/GREIT-реконструкция рассчитана, но порядок каналов и геометрия прибора не подтверждены",
        "en": "FEM/GREIT reconstruction is calculated, but device channel order and geometry are unconfirmed",
        "zh": "FEM/GREIT 重建已计算，但设备通道顺序和几何形状尚未确认",
        "vi": "Đã tính tái tạo FEM/GREIT, nhưng thứ tự kênh và hình học thiết bị chưa được xác nhận",
    },
    "monitor_quality_stale": {
        "ru": "Данные: обновление приостановлено", "en": "Data: updates paused",
        "zh": "数据：更新已暂停", "vi": "Dữ liệu: cập nhật đã tạm dừng",
    },
    "monitor_quality_unavailable": {
        "ru": "Данные недоступны", "en": "Data unavailable",
        "zh": "数据不可用", "vi": "Dữ liệu không khả dụng",
    },
    "monitor_reason_insufficient": {
        "ru": "недостаточно данных", "en": "insufficient data",
        "zh": "数据不足", "vi": "không đủ dữ liệu",
    },
    "monitor_reason_cycles": {
        "ru": "недостаточно полных дыхательных циклов", "en": "not enough complete breathing cycles",
        "zh": "完整呼吸周期不足", "vi": "không đủ chu kỳ thở hoàn chỉnh",
    },
    "monitor_reason_no_breath": {
        "ru": "дыхательный сигнал не обнаружен", "en": "no breathing signal detected",
        "zh": "未检测到呼吸信号", "vi": "không phát hiện tín hiệu thở",
    },
    "monitor_reason_regional": {
        "ru": "регионарный сигнал недоступен", "en": "regional signal unavailable",
        "zh": "区域信号不可用", "vi": "tín hiệu khu vực không khả dụng",
    },
    "monitor_reason_source": {
        "ru": "источник не передаёт данные", "en": "source is not providing data",
        "zh": "数据源未提供数据", "vi": "nguồn không cung cấp dữ liệu",
    },
    "monitor_reason_source_quality": {
        "ru": "источник сообщил низкое качество", "en": "source reported low quality",
        "zh": "数据源报告质量较低", "vi": "nguồn báo chất lượng thấp",
    },
    "monitor_reason_artifact": {
        "ru": "обнаружен артефакт движения или сигнала", "en": "motion or signal artifact detected",
        "zh": "检测到运动或信号伪影", "vi": "phát hiện nhiễu do chuyển động hoặc tín hiệu",
    },
    "monitor_reason_paused": {
        "ru": "мониторинг приостановлен", "en": "monitoring is paused",
        "zh": "监测已暂停", "vi": "giám sát đã tạm dừng",
    },
    "monitor_reason_lost": {
        "ru": "поток данных потерян", "en": "data stream lost",
        "zh": "数据流已丢失", "vi": "mất luồng dữ liệu",
    },
    "marker_dialog_title": {
        "ru": "Маркер события", "en": "Event marker",
        "zh": "事件标记", "vi": "Đánh dấu sự kiện",
    },
    "marker_correction_title": {
        "ru": "Корректирующая запись", "en": "Correction entry",
        "zh": "更正记录", "vi": "Bản ghi hiệu chỉnh",
    },
    "marker_position": {
        "ru": "Позиция исследования", "en": "Study position",
        "zh": "检查位置", "vi": "Vị trí nghiên cứu",
    },
    "marker_type": {
        "ru": "Тип", "en": "Type", "zh": "类型", "vi": "Loại",
    },
    "marker_author": {
        "ru": "Автор", "en": "Author", "zh": "作者", "vi": "Tác giả",
    },
    "marker_description": {
        "ru": "Описание", "en": "Description", "zh": "描述", "vi": "Mô tả",
    },
    "marker_description_hint": {
        "ru": "Что произошло во время мониторинга?", "en": "What happened during monitoring?",
        "zh": "监测期间发生了什么？", "vi": "Điều gì đã xảy ra trong quá trình giám sát?",
    },
    "marker_required": {
        "ru": "Укажите описание и автора.", "en": "Enter a description and author.",
        "zh": "请输入描述和作者。", "vi": "Nhập mô tả và tác giả.",
    },
    "marker_type_cough": {
        "ru": "Кашель", "en": "Cough", "zh": "咳嗽", "vi": "Ho",
    },
    "marker_type_procedure": {
        "ru": "Манипуляция", "en": "Procedure", "zh": "操作", "vi": "Thủ thuật",
    },
    "marker_type_position": {
        "ru": "Смена положения", "en": "Position change", "zh": "体位改变", "vi": "Thay đổi tư thế",
    },
    "marker_type_suction": {
        "ru": "Санация", "en": "Suction", "zh": "吸痰", "vi": "Hút đờm",
    },
    "marker_type_note": {
        "ru": "Заметка оператора", "en": "Operator note", "zh": "操作员备注", "vi": "Ghi chú người vận hành",
    },
    "marker_unavailable": {
        "ru": "Маркер можно создать только для активного исследования.",
        "en": "A marker can only be created for an active study.",
        "zh": "只能为正在进行的检查创建标记。",
        "vi": "Chỉ có thể tạo dấu cho nghiên cứu đang hoạt động.",
    },
    "marker_correction": {
        "ru": "Исправить", "en": "Correct", "zh": "更正", "vi": "Hiệu chỉnh",
    },
    "marker_corrects": {
        "ru": "Коррекция", "en": "Correction", "zh": "更正", "vi": "Hiệu chỉnh",
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
    "lung_reconstruction_map": {
        "ru": "Карта реконструкции ΔZ",
        "en": "Reconstructed ΔZ map",
        "zh": "重建 ΔZ 图",
        "vi": "Bản đồ tái tạo ΔZ",
    },
    "lung_reconstruction_tooltip": {
        "ru": "Абсолютная карта показывает относительную проводимость в условных единицах. Щёлкните по карте для переключения на ΔZ.",
        "en": "The absolute map shows relative conductivity in arbitrary units. Click the map to switch to ΔZ.",
        "zh": "绝对图显示任意单位的相对电导率。点击图像可切换到 ΔZ。",
        "vi": "Bản đồ tuyệt đối hiển thị độ dẫn điện tương đối theo đơn vị quy ước. Nhấp để chuyển sang ΔZ.",
    },
    "lung_absolute_conductivity_map": {
        "ru": "Проводимость σ (отн., а.е.)",
        "en": "Conductivity σ (relative, a.u.)",
        "zh": "电导率 σ（相对，任意单位）",
        "vi": "Độ dẫn điện σ (tương đối, đ.v.q.ư.)",
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
    "wave_rr_short": {
        "ru": "ЧД", "en": "RR", "zh": "呼吸率", "vi": "NT",
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
    "study_stop_title": {
        "ru": "Завершение исследования", "en": "Complete study",
        "zh": "结束检查", "vi": "Kết thúc nghiên cứu",
    },
    "study_stop_confirm": {
        "ru": "Завершить активное исследование? После завершения оно будет доступно только для просмотра и экспорта.",
        "en": "Complete the active study? Afterwards it will be available only for viewing and export.",
        "zh": "结束当前检查？结束后只能查看和导出。",
        "vi": "Kết thúc nghiên cứu đang hoạt động? Sau đó chỉ có thể xem và xuất.",
    },
    "study_action_error_title": {
        "ru": "Действие недоступно", "en": "Action unavailable",
        "zh": "操作不可用", "vi": "Thao tác không khả dụng",
    },
    "study_prepare_first": {
        "ru": "Сначала сохраните пациента и привяжите новое исследование.",
        "en": "Save the patient and link a new study first.",
        "zh": "请先保存患者并关联新的检查。",
        "vi": "Trước tiên hãy lưu bệnh nhân và liên kết nghiên cứu mới.",
    },
    "study_invalid_transition": {
        "ru": "Переход в это состояние исследования недопустим.",
        "en": "This study state transition is not allowed.",
        "zh": "不允许转换到此检查状态。",
        "vi": "Không cho phép chuyển sang trạng thái nghiên cứu này.",
    },
    "study_select_patient_first": {
        "ru": "Сначала сохраните или выберите пациента.",
        "en": "Save or select a patient first.",
        "zh": "请先保存或选择患者。",
        "vi": "Trước tiên hãy lưu hoặc chọn bệnh nhân.",
    },
    "study_finish_current_first": {
        "ru": "Сначала завершите текущее исследование.",
        "en": "Complete the current study first.",
        "zh": "请先结束当前检查。",
        "vi": "Hãy kết thúc nghiên cứu hiện tại trước.",
    },
    "study_active_other_patient": {
        "ru": "Нельзя сменить пациента во время активного исследования.",
        "en": "The patient cannot be changed during an active study.",
        "zh": "活动检查期间不能更换患者。",
        "vi": "Không thể đổi bệnh nhân trong khi nghiên cứu đang hoạt động.",
    },
    "study_linked_title": {
        "ru": "Исследование подготовлено", "en": "Study prepared",
        "zh": "检查已准备", "vi": "Nghiên cứu đã sẵn sàng",
    },
    "study_linked_message": {
        "ru": "Новое исследование привязано к выбранному пациенту и готово к запуску.",
        "en": "A new study is linked to the selected patient and ready to start.",
        "zh": "新检查已关联到所选患者，可以开始。",
        "vi": "Nghiên cứu mới đã được liên kết với bệnh nhân và sẵn sàng bắt đầu.",
    },
    "study_status_draft": {"ru": "Черновик", "en": "Draft", "zh": "草稿", "vi": "Bản nháp"},
    "study_status_ready": {"ru": "Готово", "en": "Ready", "zh": "就绪", "vi": "Sẵn sàng"},
    "study_status_running": {"ru": "Выполняется", "en": "Running", "zh": "进行中", "vi": "Đang chạy"},
    "study_status_paused": {"ru": "Приостановлено", "en": "Paused", "zh": "已暂停", "vi": "Tạm dừng"},
    "study_status_completed": {"ru": "Завершено", "en": "Completed", "zh": "已完成", "vi": "Hoàn thành"},
    "study_status_failed": {"ru": "Завершено аварийно", "en": "Failed", "zh": "异常结束", "vi": "Thất bại"},
    "study_conclusion_missing": {
        "ru": "Заключение не указано", "en": "No conclusion provided",
        "zh": "未提供结论", "vi": "Chưa có kết luận",
    },
    "study_conclusion_emergency": {
        "ru": "Аварийное завершение", "en": "Emergency termination",
        "zh": "紧急终止", "vi": "Kết thúc khẩn cấp",
    },
    "study_conclusion_restart": {
        "ru": "Прервано перезапуском приложения", "en": "Interrupted by application restart",
        "zh": "因应用重启而中断", "vi": "Bị gián đoạn do khởi động lại ứng dụng",
    },
    "study_conclusion_application_closed": {
        "ru": "Завершено при закрытии приложения",
        "en": "Completed when the application was closed",
        "zh": "应用关闭时结束",
        "vi": "Hoàn tất khi đóng ứng dụng",
    },
    "study_details_title": {
        "ru": "Исследование ЭИТ", "en": "EIT study",
        "zh": "EIT 检查", "vi": "Nghiên cứu EIT",
    },
    "study_details_date": {"ru": "Дата", "en": "Date", "zh": "日期", "vi": "Ngày"},
    "study_details_duration": {"ru": "Длительность", "en": "Duration", "zh": "时长", "vi": "Thời lượng"},
    "study_details_status": {"ru": "Статус", "en": "Status", "zh": "状态", "vi": "Trạng thái"},
    "study_details_conclusion": {"ru": "Заключение", "en": "Conclusion", "zh": "结论", "vi": "Kết luận"},
    "study_details_author": {"ru": "Автор", "en": "Author", "zh": "作者", "vi": "Tác giả"},

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
        "ru": "МКБ",
        "en": "ICD",
        "zh": "ICD",
        "vi": "ICD",
    },
    "pat_icd_code_10": {"ru": "МКБ-10", "en": "ICD-10", "zh": "ICD-10", "vi": "ICD-10"},
    "pat_icd_code_11": {"ru": "МКБ-11", "en": "ICD-11", "zh": "ICD-11", "vi": "ICD-11"},
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
    "pat_history_empty": {
        "ru": "У выбранного пациента пока нет исследований",
        "en": "The selected patient has no studies yet",
        "zh": "所选患者尚无检查记录",
        "vi": "Bệnh nhân đã chọn chưa có nghiên cứu",
    },
    "pat_icd_dialog_title": {
        "ru": "Выбор диагноза",
        "en": "Select diagnosis",
        "zh": "选择诊断",
        "vi": "Chọn chẩn đoán",
    },
    "pat_icd_search": {
        "ru": "Поиск по коду или названию",
        "en": "Search by code or title",
        "zh": "按代码或名称搜索",
        "vi": "Tìm theo mã hoặc tên",
    },
    "pat_invalid_diagnosis": {
        "ru": "Выберите диагноз из активного справочника МКБ",
        "en": "Select a diagnosis from the active ICD catalogue",
        "zh": "请从当前 ICD 目录中选择诊断",
        "vi": "Chọn chẩn đoán từ danh mục ICD đang hoạt động",
    },
    "pat_ivl_dialog_title": {
        "ru": "Параметры ИВЛ",
        "en": "Ventilation parameters",
        "zh": "机械通气参数",
        "vi": "Thông số thở máy",
    },
    "pat_ivl_mode": {"ru": "Режим", "en": "Mode", "zh": "模式", "vi": "Chế độ"},
    "pat_ivl_fio2": {"ru": "FiO₂", "en": "FiO₂", "zh": "FiO₂", "vi": "FiO₂"},
    "pat_ivl_peep": {"ru": "ПДКВ", "en": "PEEP", "zh": "PEEP", "vi": "PEEP"},
    "pat_unsaved_title": {
        "ru": "Несохранённые изменения", "en": "Unsaved changes",
        "zh": "未保存的更改", "vi": "Thay đổi chưa lưu",
    },
    "pat_unsaved_message": {
        "ru": "Закрыть карточку и отбросить несохранённые изменения?",
        "en": "Close the card and discard unsaved changes?",
        "zh": "关闭病历并放弃未保存的更改？",
        "vi": "Đóng hồ sơ và bỏ các thay đổi chưa lưu?",
    },
    "pat_unsaved_discard": {
        "ru": "Не сохранять",
        "en": "Don't save",
        "zh": "不保存",
        "vi": "Không lưu",
    },
    "pat_unsaved_cancel": {
        "ru": "Отмена",
        "en": "Cancel",
        "zh": "取消",
        "vi": "Hủy",
    },
    "pat_validation_title": {
        "ru": "Проверьте данные", "en": "Check the data",
        "zh": "检查数据", "vi": "Kiểm tra dữ liệu",
    },
    "pat_validation_message": {
        "ru": "Заполните обязательные поля корректными уникальными значениями.",
        "en": "Fill in required fields with valid unique values.",
        "zh": "请使用有效且唯一的值填写必填字段。",
        "vi": "Điền các trường bắt buộc bằng giá trị hợp lệ và duy nhất.",
    },
    "pat_error_required": {
        "ru": "Обязательное поле.", "en": "This field is required.",
        "zh": "此字段为必填项。", "vi": "Trường này là bắt buộc.",
    },
    "pat_error_name_format": {
        "ru": "Используйте имя без цифр.", "en": "Use a name without digits.",
        "zh": "姓名中不能包含数字。", "vi": "Tên không được chứa chữ số.",
    },
    "pat_error_birth_future": {
        "ru": "Дата рождения не может быть в будущем.",
        "en": "The date of birth cannot be in the future.",
        "zh": "出生日期不能晚于今天。", "vi": "Ngày sinh không thể ở tương lai.",
    },
    "pat_error_id_format": {
        "ru": "Введите от 3 до 32 латинских букв, цифр или символов . _ -",
        "en": "Enter 3–32 Latin letters, digits, or . _ -",
        "zh": "请输入 3–32 个拉丁字母、数字或 . _ -",
        "vi": "Nhập 3–32 chữ cái Latinh, chữ số hoặc . _ -",
    },
    "pat_error_duplicate": {
        "ru": "Такое значение уже используется.",
        "en": "This value is already in use.",
        "zh": "该值已被使用。", "vi": "Giá trị này đã được sử dụng.",
    },
    "pat_error_record_format": {
        "ru": "Введите номер истории болезни (до 64 символов).",
        "en": "Enter a medical record number (up to 64 characters).",
        "zh": "请输入病历号（最多 64 个字符）。",
        "vi": "Nhập số hồ sơ bệnh án (tối đa 64 ký tự).",
    },
    "pat_error_weight_range": {
        "ru": "Введите массу от 0,5 до 500 кг.",
        "en": "Enter a weight from 0.5 to 500 kg.",
        "zh": "请输入 0.5 至 500 千克的体重。",
        "vi": "Nhập cân nặng từ 0,5 đến 500 kg.",
    },
    "pat_error_height_range": {
        "ru": "Введите рост от 20 до 250 см.",
        "en": "Enter a height from 20 to 250 cm.",
        "zh": "请输入 20 至 250 厘米的身高。",
        "vi": "Nhập chiều cao từ 20 đến 250 cm.",
    },
    "pat_error_chest_range": {
        "ru": "Введите охват грудной клетки от 20 до 250 см.",
        "en": "Enter a chest circumference from 20 to 250 cm.",
        "zh": "请输入 20 至 250 厘米的胸围。",
        "vi": "Nhập vòng ngực từ 20 đến 250 cm.",
    },
    "pat_error_invalid_value": {
        "ru": "Проверьте значение поля.", "en": "Check this field value.",
        "zh": "请检查该字段的值。", "vi": "Kiểm tra giá trị của trường này.",
    },
    "pat_saved_title": {
        "ru": "Карточка сохранена", "en": "Card saved",
        "zh": "病历已保存", "vi": "Đã lưu hồ sơ",
    },
    "pat_saved_message": {
        "ru": "Данные пациента сохранены.", "en": "Patient data has been saved.",
        "zh": "患者数据已保存。", "vi": "Đã lưu dữ liệu bệnh nhân.",
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
    "sq_status_waiting": {
        "ru": "Ожидание данных диагностики электродов",
        "en": "Waiting for electrode diagnostics",
        "zh": "正在等待电极诊断数据",
        "vi": "Đang chờ dữ liệu chẩn đoán điện cực",
    },
    "sq_status_ready": {
        "ru": "Пригодных измерений: {percent}% · старт разрешён",
        "en": "Usable measurements: {percent}% · start allowed",
        "zh": "可用测量：{percent}% · 允许开始",
        "vi": "Phép đo sử dụng được: {percent}% · được phép bắt đầu",
    },
    "sq_status_blocked": {
        "ru": "Пригодных измерений: {percent}% · старт заблокирован",
        "en": "Usable measurements: {percent}% · start blocked",
        "zh": "可用测量：{percent}% · 已阻止开始",
        "vi": "Phép đo sử dụng được: {percent}% · đã chặn bắt đầu",
    },
    "sq_calibration_running": {
        "ru": "Выполняется калибровка…",
        "en": "Calibration in progress…",
        "zh": "正在校准…",
        "vi": "Đang hiệu chỉnh…",
    },
    "sq_calibration_success": {
        "ru": "Калибровка завершена и сохранена в исследовании",
        "en": "Calibration completed and saved in the study",
        "zh": "校准完成并已保存到检查中",
        "vi": "Hiệu chỉnh hoàn tất và đã lưu vào nghiên cứu",
    },
    "sq_calibration_failed": {
        "ru": "Калибровка отклонена: проверьте электроды {electrodes}",
        "en": "Calibration failed: check electrodes {electrodes}",
        "zh": "校准失败：请检查电极 {electrodes}",
        "vi": "Hiệu chỉnh thất bại: kiểm tra điện cực {electrodes}",
    },
    "sq_calibration_no_study": {
        "ru": "Сначала подготовьте исследование пациента",
        "en": "Prepare a patient study before calibration",
        "zh": "请先准备患者检查",
        "vi": "Hãy chuẩn bị nghiên cứu bệnh nhân trước khi hiệu chỉnh",
    },
    "study_contact_quality_blocked": {
        "ru": "Старт запрещён: исправьте критически плохой контакт электродов.",
        "en": "Start blocked: correct critically poor electrode contact.",
        "zh": "无法开始：请修复严重不良的电极接触。",
        "vi": "Đã chặn bắt đầu: khắc phục tiếp xúc điện cực quá kém.",
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
    "eit_electrode_order_label": {
        "ru": "Порядок нумерации электродов",
        "en": "Electrode numbering order",
        "zh": "电极编号顺序",
        "vi": "Thứ tự đánh số điện cực",
    },
    "eit_electrode_order_right_ccw": {
        "ru": "№1 справа → против часовой стрелки",
        "en": "No. 1 right → counter-clockwise",
        "zh": "1号在右侧 → 逆时针",
        "vi": "Số 1 bên phải → ngược chiều kim đồng hồ",
    },
    "eit_electrode_order_right_cw": {
        "ru": "№1 справа → по часовой стрелке",
        "en": "No. 1 right → clockwise",
        "zh": "1号在右侧 → 顺时针",
        "vi": "Số 1 bên phải → theo chiều kim đồng hồ",
    },
    "eit_electrode_order_sternum_cw": {
        "ru": "№1 у грудины → по часовой стрелке",
        "en": "No. 1 at sternum → clockwise",
        "zh": "1号在胸骨处 → 顺时针",
        "vi": "Số 1 tại xương ức → theo chiều kim đồng hồ",
    },
    "eit_electrode_order_sternum_ccw": {
        "ru": "№1 у грудины → против часовой стрелки",
        "en": "No. 1 at sternum → counter-clockwise",
        "zh": "1号在胸骨处 → 逆时针",
        "vi": "Số 1 tại xương ức → ngược chiều kim đồng hồ",
    },
    "eit_measurement_sequence_label": {
        "ru": "Последовательность измерений (16×13)",
        "en": "Measurement sequence (16×13)",
        "zh": "测量序列（16×13）",
        "vi": "Trình tự đo (16×13)",
    },
    "eit_sequence_adjacent_fixed": {
        "ru": "Смежная: фиксированный порядок",
        "en": "Adjacent: fixed order",
        "zh": "相邻：固定顺序",
        "vi": "Liền kề: thứ tự cố định",
    },
    "eit_sequence_adjacent_rotating": {
        "ru": "Смежная: вращающийся порядок (EIDORS)",
        "en": "Adjacent: rotating order (EIDORS)",
        "zh": "相邻：旋转顺序（EIDORS）",
        "vi": "Liền kề: thứ tự xoay (EIDORS)",
    },
    "eit_sequence_adjacent_reciprocal": {
        "ru": "Смежная: взаимный порядок",
        "en": "Adjacent: reciprocal order",
        "zh": "相邻：互易顺序",
        "vi": "Liền kề: thứ tự tương hỗ",
    },
    "eit_sequence_adjacent_reversed": {
        "ru": "Смежная: обратный обход",
        "en": "Adjacent: reverse scan",
        "zh": "相邻：反向扫描",
        "vi": "Liền kề: quét ngược",
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
    "eit_reset_confirm_title": {
        "ru": "Сброс настроек ЭИТ",
        "en": "Reset EIT settings",
        "zh": "重置 EIT 设置",
        "vi": "Đặt lại cài đặt EIT",
    },
    "eit_reset_confirm_message": {
        "ru": "Восстановить настройки ЭИТ по умолчанию?",
        "en": "Restore the default EIT settings?",
        "zh": "恢复默认 EIT 设置吗？",
        "vi": "Khôi phục cài đặt EIT mặc định?",
    },

    # ── Export data screen ─────────────────────────────────────────────────
    "exp_format_title": {
        "ru": "Формат экспорта",
        "en": "Export format",
        "zh": "导出格式",
        "vi": "Định dạng xuất",
    },
    "exp_data_title": {
        "ru": "Состав данных",
        "en": "Data categories",
        "zh": "数据类别",
        "vi": "Danh mục dữ liệu",
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
    "eit_diagnosis_catalog_label": {
        "ru": "Справочник диагнозов",
        "en": "Diagnosis catalogue",
        "zh": "诊断目录",
        "vi": "Danh mục chẩn đoán",
    },
    "eit_icd10": {"ru": "МКБ-10", "en": "ICD-10", "zh": "ICD-10", "vi": "ICD-10"},
    "eit_icd11": {"ru": "МКБ-11", "en": "ICD-11", "zh": "ICD-11", "vi": "ICD-11"},
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
    "analysis_interval": {
        "ru": "Интервал", "en": "Interval", "zh": "区间", "vi": "Khoảng",
    },
    "analysis_cycles": {
        "ru": "Циклы", "en": "Breaths", "zh": "呼吸周期", "vi": "Chu kỳ",
    },
    "analysis_all_cycles": {
        "ru": "Все", "en": "All", "zh": "全部", "vi": "Tất cả",
    },
    "analysis_seconds_short": {
        "ru": "с", "en": "s", "zh": "秒", "vi": "giây",
    },
    "analysis_quality": {
        "ru": "Качество", "en": "Quality", "zh": "质量", "vi": "Chất lượng",
    },
    "analysis_cycles_found": {
        "ru": "циклов", "en": "cycles", "zh": "周期", "vi": "chu kỳ",
    },
    "analysis_samples": {
        "ru": "отсч.", "en": "samples", "zh": "样本", "vi": "mẫu",
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
    "analysis_bt_undetermined": {
        "ru": "Не определено", "en": "Undetermined",
        "zh": "未确定", "vi": "Chưa xác định",
    },
    "analysis_manual_type": {
        "ru": "Ручная отметка специалиста", "en": "Specialist manual assessment",
        "zh": "专家手动评估", "vi": "Đánh giá thủ công của chuyên gia",
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

    # ── Shared UI presentation ────────────────────────────────────────────
    "common_ok": {"ru": "ОК", "en": "OK", "zh": "确定", "vi": "Đồng ý"},
    "common_cancel": {"ru": "Отмена", "en": "Cancel", "zh": "取消", "vi": "Hủy"},
    "common_yes": {"ru": "Да", "en": "Yes", "zh": "是", "vi": "Có"},
    "common_no": {"ru": "Нет", "en": "No", "zh": "否", "vi": "Không"},
    "monitor_reason_unknown": {
        "ru": "причина не определена", "en": "reason not specified",
        "zh": "原因未指定", "vi": "chưa xác định nguyên nhân",
    },
    "ui_reason_label": {"ru": "Причина", "en": "Reason", "zh": "原因", "vi": "Nguyên nhân"},
    "ui_algorithm_version": {
        "ru": "Версия алгоритма", "en": "Algorithm version",
        "zh": "算法版本", "vi": "Phiên bản thuật toán",
    },
    "study_status_unknown": {
        "ru": "Статус не определён", "en": "Unknown status",
        "zh": "状态未知", "vi": "Trạng thái không xác định",
    },
    "study_conclusion_start_failed": {
        "ru": "Не удалось начать мониторинг", "en": "Monitoring failed to start",
        "zh": "监测启动失败", "vi": "Không thể bắt đầu giám sát",
    },
    "analysis_param_sample_rate": {
        "ru": "Частота дискретизации", "en": "Sample rate",
        "zh": "采样率", "vi": "Tần số lấy mẫu",
    },
    "analysis_param_smoothing": {
        "ru": "Отсчётов сглаживания", "en": "Smoothing samples",
        "zh": "平滑样本数", "vi": "Số mẫu làm mượt",
    },
    "analysis_param_min_cycles": {
        "ru": "Минимум полных циклов", "en": "Minimum complete cycles",
        "zh": "最少完整周期", "vi": "Số chu kỳ hoàn chỉnh tối thiểu",
    },
    "analysis_param_rr_range": {
        "ru": "Диапазон ЧД", "en": "Respiratory-rate range",
        "zh": "呼吸频率范围", "vi": "Khoảng nhịp thở",
    },
    "analysis_unit_hz": {"ru": "Гц", "en": "Hz", "zh": "赫兹", "vi": "Hz"},
    "sys_mode_simulation": {
        "ru": "Симуляция", "en": "Simulation", "zh": "模拟", "vi": "Mô phỏng",
    },
    "sys_mode_device": {
        "ru": "Устройство", "en": "Device", "zh": "设备", "vi": "Thiết bị",
    },
    "sys_mode_fromfile": {
        "ru": "Из файла", "en": "From file", "zh": "来自文件", "vi": "Từ tệp",
    },
    "sys_not_configured": {
        "ru": "не настроено", "en": "not configured",
        "zh": "未配置", "vi": "chưa cấu hình",
    },
    "svc_search_placeholder": {
        "ru": "Поиск", "en": "Search", "zh": "搜索", "vi": "Tìm kiếm",
    },
    "exp_category_metadata": {
        "ru": "Метаданные и пациент", "en": "Metadata and patient",
        "zh": "元数据和患者", "vi": "Siêu dữ liệu và bệnh nhân",
    },
    "exp_category_metrics": {
        "ru": "Итоговые показатели", "en": "Summary metrics",
        "zh": "汇总指标", "vi": "Chỉ số tổng hợp",
    },
    "exp_category_trends": {"ru": "Тренды", "en": "Trends", "zh": "趋势", "vi": "Xu hướng"},
    "exp_category_events": {"ru": "События", "en": "Events", "zh": "事件", "vi": "Sự kiện"},
    "exp_category_raw": {
        "ru": "Сырые данные", "en": "Raw data", "zh": "原始数据", "vi": "Dữ liệu thô",
    },
    "exp_privacy_warning": {
        "ru": "Экспорт может содержать персональные данные.",
        "en": "The export may contain personal data.",
        "zh": "导出内容可能包含个人数据。",
        "vi": "Dữ liệu xuất có thể chứa thông tin cá nhân.",
    },
    "exp_no_studies": {
        "ru": "Нет сохранённых исследований", "en": "No saved studies",
        "zh": "没有已保存的检查", "vi": "Không có nghiên cứu đã lưu",
    },
    "exp_estimate": {
        "ru": "Выбрано исследований: {count}; оценка размера: {size}",
        "en": "Selected studies: {count}; estimated size: {size}",
        "zh": "已选检查：{count}；预计大小：{size}",
        "vi": "Nghiên cứu đã chọn: {count}; dung lượng ước tính: {size}",
    },
    "exp_detail_patient": {"ru": "Пациент", "en": "Patient", "zh": "患者", "vi": "Bệnh nhân"},
    "exp_detail_status": {"ru": "Статус", "en": "Status", "zh": "状态", "vi": "Trạng thái"},
    "exp_detail_created": {"ru": "Создано", "en": "Created", "zh": "创建时间", "vi": "Đã tạo"},
    "exp_detail_conclusion": {"ru": "Заключение", "en": "Conclusion", "zh": "结论", "vi": "Kết luận"},
    "exp_selection_error": {
        "ru": "Выберите хотя бы одно исследование и категорию данных.",
        "en": "Select at least one study and one data category.",
        "zh": "请至少选择一项检查和一个数据类别。",
        "vi": "Chọn ít nhất một nghiên cứu và một loại dữ liệu.",
    },
    "exp_generation_error": {
        "ru": "Не удалось сформировать экспорт. Подробности записаны в технический журнал.",
        "en": "The export could not be generated. Details were written to the technical log.",
        "zh": "无法生成导出。详细信息已写入技术日志。",
        "vi": "Không thể tạo bản xuất. Chi tiết đã được ghi vào nhật ký kỹ thuật.",
    },
    "exp_saved": {
        "ru": "Экспорт сохранён:\n{path}", "en": "Export saved:\n{path}",
        "zh": "导出已保存：\n{path}", "vi": "Đã lưu bản xuất:\n{path}",
    },
    "rep_default_title": {
        "ru": "Отчёт ЭИТ", "en": "EIT report", "zh": "EIT 报告", "vi": "Báo cáo EIT",
    },
    "rep_generation_error": {
        "ru": "Не удалось сформировать отчёт. Проверьте выбранное исследование и период.",
        "en": "The report could not be generated. Check the selected study and period.",
        "zh": "无法生成报告。请检查所选检查和时间段。",
        "vi": "Không thể tạo báo cáo. Hãy kiểm tra nghiên cứu và khoảng thời gian đã chọn.",
    },
    "rep_preview_error": {
        "ru": "Не удалось открыть предварительный просмотр отчёта.",
        "en": "The report preview could not be opened.",
        "zh": "无法打开报告预览。", "vi": "Không thể mở bản xem trước báo cáo.",
    },
    "rep_print_error": {
        "ru": "Не удалось напечатать отчёт.", "en": "The report could not be printed.",
        "zh": "无法打印报告。", "vi": "Không thể in báo cáo.",
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
