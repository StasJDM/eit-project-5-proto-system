# Таблица переводов интерфейса / UI Translation Table

> **Источник правды** — файл `app/i18n.py` (словарь `STRINGS`).  
> Эта таблица синхронизируется с кодом вручную.  
> При добавлении нового элемента интерфейса — добавить строку в обе таблицы.

---

## Правило добавления нового элемента

1. Придумать стабильный ключ на английском (snake_case): `my_button_label`
2. Добавить запись в `STRINGS` в `app/i18n.py` со всеми 4 языками
3. Добавить строку в таблицу ниже
4. В виджете использовать `t("my_button_label")` вместо хардкода строки
5. Реализовать метод `retranslate()` в виджете и подключить к `i18n.language_changed`

---

## Коды языков

| Код | Язык |
|-----|------|
| RU | Русский |
| EN | English |
| ZN | 中文 |
| VI | Tiếng Việt |

---

## Таблица строк

| Ключ | Русский | English | 中文 | Tiếng Việt |
|---|---|---|---|---|
| **Приложение** | | | | |
| `app_title` | ЭИТ — Монитор пациента | EIT — Patient Monitor | EIT — 患者监护仪 | EIT — Màn hình bệnh nhân |
| **Верхняя панель (HeaderBar)** | | | | |
| `hdr_adult` | 👤 Взрослый | 👤 Adult | 👤 成人 | 👤 Người lớn |
| `hdr_alarm` | ⚠  СИГНАЛ ТРЕВОГИ | ⚠  ALARM | ⚠  警报 | ⚠  BÁO ĐỘNG |
| `hdr_breath_normal` | ТИП ДЫХАНИЯ: НОРМАЛЬНОЕ | BREATHING TYPE: NORMAL | 呼吸类型：正常 | LOẠI THỞ: BÌNH THƯỜNG |
| `hdr_child` | 🧒 Ребёнок | 🧒 Child | 🧒 儿童 | 🧒 Trẻ em |
| `hdr_menu_tooltip` | Главное меню | Main Menu | 主菜单 | Menu chính |
| **Навигационная панель (NavPanel)** | | | | |
| `nav_analysis` | 🔬  Анализ | 🔬  Analysis | 🔬  分析 | 🔬  Phân tích |
| `nav_debug` | 🛠  Отладка и Тестирование | 🛠  Debug & Testing | 🛠  调试与 测试 | 🛠  Gỡ lỗi & Kiểm tra |
| `nav_eit_settings` | ⚙  Настройки ЭИТ | ⚙  EIT Settings | ⚙  EIT 设置 | ⚙  Cài đặt EIT |
| `nav_export` | 💾  Экспорт данных | 💾  Export data | 💾  导出 数据 | 💾  Xuất dữ liệu |
| `nav_main` | 🏠  Главное окно | 🏠  Main window | 🏠  主 窗口 | 🏠  Cửa sổ chính |
| `nav_patient` | 👤  Пациент | 👤  Patient | 👤  患者 | 👤  Bệnh nhân |
| `nav_reports` | 📋  Отчёты | 📋  Reports | 📋  报告 | 📋  Báo cáo |
| `nav_service` | 🔧  Служебная информация | 🔧  Service information | 🔧  服务 信息 | 🔧  Thông tin dịch vụ |
| `nav_signal_quality` | Качество сигнала ЭС | Signal quality ES | 信号 质量 | Chất lượng tín hiệu |
| `nav_system` | ℹ  Системная информация | ℹ  System information | ℹ  系统 信息 | ℹ  Thông tin hệ thống |
| `nav_trends` | 📈  Тренды | 📈  Trends | 📈  趋势 | 📈  Xu hướng |
| **Визуализация лёгких (LungVizWidget)** | | | | |
| `lung_breath_cycle` | Дыхательный цикл | Breathing cycle | 呼吸周期 | Chu kỳ thở |
| **Панель кривых (WaveformPanel)** | | | | |
| `wave_event_marker` | ⚑  МАРКЕР СОБЫТИЙ | ⚑  EVENT MARKER | ⚑  事件标记 | ⚑  ĐÁNH DẤU SỰ KIỆN |
| `wave_l_label` | L  Левое лёгкое | L  Left lung | L  左肺 | L  Phổi trái |
| `wave_r_label` | R  Правое лёгкое | R  Right lung | R  右肺 | R  Phổi phải |
| `wave_rr_unit` | вд/мин | br/min | 次/分 | lần/phút |
| `wave_t_label` | T  Глобальная аэрация | T  Global aeration | T  全局通气 | T  Thông khí toàn thể |
| `wave_trend` | Тренд | Trend | 趋势 | Xu hướng |
| **Левая панель / общие кнопки** | | | | |
| `btn_start` | ▶  СТАРТ | ▶  START | ▶  开始 | ▶  BẮT ĐẦU |
| `btn_stop` | ⏹  СТОП | ⏹  STOP | ⏹  停止 | ⏹  DỪNG |
| `param_eit_duration` | Длительность ЭИТ: | EIT Duration: | EIT持续时间: | Thời gian EIT: |
| `param_es_time` | Время использ. ЭС: | ES Usage Time: | ES使用时间: | Thời gian sử dụng ES: |
| **Заголовки экранов** | | | | |
| `screen_analysis` | АНАЛИЗ | ANALYSIS | 分析 | PHÂN TÍCH |
| `screen_debug` | ОТЛАДКА И ТЕСТИРОВАНИЕ | DEBUG AND TESTING | 调试与测试 | GỠ LỖI VÀ KIỂM TRA |
| `screen_eit_settings` | НАСТРОЙКИ ЭИТ | EIT SETTINGS | EIT设置 | CÀI ĐẶT EIT |
| `screen_export` | ЭКСПОРТ ДАННЫХ | EXPORT DATA | 导出数据 | XUẤT DỮ LIỆU |
| `screen_main` | ГЛАВНОЕ ОКНО | MAIN WINDOW | 主窗口 | CỬA SỔ CHÍNH |
| `screen_patient` | ПАЦИЕНТ | PATIENT | 患者 | BỆNH NHÂN |
| `screen_reports` | ОТЧЁТЫ | REPORTS | 报告 | BÁO CÁO |
| `screen_service` | СЛУЖЕБНАЯ ИНФОРМАЦИЯ | SERVICE INFORMATION | 服务信息 | THÔNG TIN DỊCH VỤ |
| `screen_system` | СИСТЕМНАЯ ИНФОРМАЦИЯ | SYSTEM INFORMATION | 系统信息 | THÔNG TIN HỆ THỐNG |
| `screen_trends` | ТРЕНДЫ | TRENDS | 趋势 | XU HƯỚNG |
| **Подзаголовки экранов** | | | | |
| `sub_analysis` | Детальный анализ параметров вентиляции | Detailed ventilation parameter analysis | 详细通气参数分析 | Phân tích chi tiết các thông số thông khí |
| `sub_debug` | Инструменты диагностики и тестирования системы | System diagnostics and testing tools | 系统诊断和测试工具 | Công cụ chẩn đoán và kiểm tra hệ thống |
| `sub_eit_settings` | Конфигурация параметров электроимпедансной томографии | Electrical impedance tomography configuration | 电阻抗断层扫描配置 | Cấu hình chụp cắt lớp điện trở |
| `sub_export` | Экспорт данных мониторинга в внешние форматы | Export monitoring data to external formats | 将监测数据导出为外部格式 | Xuất dữ liệu giám sát sang định dạng ngoài |
| `sub_in_development` | В разработке | In development | 开发中 | Đang phát triển |
| `sub_patient` | Ввод и редактирование данных пациента | Enter and edit patient data | 输入和编辑患者数据 | Nhập và chỉnh sửa dữ liệu bệnh nhân |
| `sub_reports` | Формирование и просмотр клинических отчётов | Generate and view clinical reports | 生成和查看临床报告 | Tạo và xem báo cáo lâm sàng |
| `sub_service` | Протоколирование неблагоприятных событий | Adverse event logging | 不良事件记录 | Ghi nhật ký sự kiện bất lợi |
| `sub_trends` | Тренды глобальной и регионарной аэрации лёгких | Global and regional lung aeration trends | 全局和区域肺通气趋势 | Xu hướng thông khí phổi toàn thể và khu vực |
| **Экран «Пациент»** | | | | |
| `pat_accompany_diag` | Диагноз сопутствующий | Accompanying diagnosis | 伴随诊断 | Chẩn đoán kèm theo |
| `pat_age` | Полных лет | Age (full years) | 周岁 | Tuổi (tròn) |
| `pat_assign_id` | Присвоить код ID | Assign ID code | 分配ID代码 | Gán mã ID |
| `pat_card_title` | Карточка пациента | Patient card | 患者卡 | Thẻ bệnh nhân |
| `pat_chest` | Охват грудной клетки, см | Chest circumference, cm | 胸围 (厘米) | Vòng ngực (cm) |
| `pat_clinical_title` | Клинические данные | Clinical data | 临床数据 | Dữ liệu lâm sàng |
| `pat_details` | Подробнее | Details | 详情 | Chi tiết |
| `pat_dob` | Дата рождения | Date of birth | 出生日期 | Ngày sinh |
| `pat_first_name` | Имя | First name | 名 | Tên |
| `pat_gender` | Пол | Gender | 性别 | Giới tính |
| `pat_gender_f` | Женский | Female | 女 | Nữ |
| `pat_gender_m` | Мужской | Male | 男 | Nam |
| `pat_height` | Рост, см | Height, cm | 身高 (厘米) | Chiều cao (cm) |
| `pat_icd_code` | МКБ-11 | ICD-11 | ICD-11 | ICD-11 |
| `pat_id` | ID | ID | ID | ID |
| `pat_ivl` | ИВЛ | Mechanical ventilation | 机械通气 | Thở máy |
| `pat_last_name` | Фамилия | Last name | 姓 | Họ |
| `pat_link_study` | Привязать текущее исследование к выбранному пациенту | Link current study to selected patient | 将当前检查与 所选患者关联 | Liên kết nghiên cứu hiện tại với bệnh nhân đã chọn |
| `pat_load_dicom` | Загрузить снимок DICOM | Load DICOM image | 加载DICOM图像 | Tải ảnh DICOM |
| `pat_lung_morph` | Морфология лёгких (определить границы) | Lung morphology (define boundaries) | 肺形态学 (确定边界) | Hình thái phổi (xác định ranh giới) |
| `pat_main_diag` | Диагноз основной | Main diagnosis | 主要诊断 | Chẩn đoán chính |
| `pat_save_card` | Сохранить карточку | Save card | 保存档案 | Lưu hồ sơ |
| `pat_no` | Нет | No | 否 | Không |
| `pat_patronymic` | Отчество | Patronymic | 父名 | Tên đệm |
| `pat_personal_title` | Персонализация | Personalization | 个性化 | Cá nhân hóa |
| `pat_prev_study` | Предыдущее исследование ЭИТ | Previous EIT study | 上次EIT检查 | Nghiên cứu EIT trước |
| `pat_preview` | Предварительный просмотр | Preview | 预览 | Xem trước |
| `pat_record_num` | Номер истории болезни | Medical record № | 病历号 | Số hồ sơ bệnh án |
| `pat_weight` | Вес, кг | Weight, kg | 体重 (千克) | Cân nặng (kg) |
| `pat_yes` | Да | Yes | 是 | Có |
| **Экран «Тренды»** | | | | |
| `trends_btn_exit` | Выход | Exit | 退出 | Thoát |
| `trends_btn_express` | Экспресс-мониторинг | Express monitoring | 快速监测 | Giám sát nhanh |
| `trends_btn_marker` | Маркер событий | Event marker | 事件标记 | Đánh dấu sự kiện |
| `trends_btn_scale` | Масштаб | Scale | 缩放 | Tỉ lệ |
| `trends_dz` | ΔZ,% | ΔZ,% | ΔZ,% | ΔZ,% |
| `trends_global_label` | GLOBAL | GLOBAL | 全局 | TOÀN THỂ |
| `trends_left_short` | Левое лёгкое (L) | Left lung (L) | 左肺 (L) | Phổi trái (L) |
| `trends_reg_label` | REG | REG | 区域 | KHU VỰC |
| `trends_right_short` | Правое лёгкое (R) | Right lung (R) | 右肺 (R) | Phổi phải (R) |
| `trends_tab_all` | Все тренды АЭРАЦИИ | All Aeration Trends | 所有通气趋势 | Tất cả xu hướng thông khí |
| `trends_tab_global` | Тренд ГЛОБАЛЬНОЙ аэрации | GLOBAL Aeration Trend | 全局通气趋势 | Xu hướng thông khí TOÀN THỂ |
| `trends_tab_regional` | Тренд РЕГИОНАРНОЙ аэрации | REGIONAL Aeration Trend | 区域通气趋势 | Xu hướng thông khí KHU VỰC |
| `trends_table` | Таблица | Table | 表格 | Bảng |
| `trends_time_hours` | Время, часы | Time, hours | 时间（小时） | Thời gian, giờ |
| `trends_time_min` | Время, минуты | Time, minutes | 时间（分钟） | Thời gian, phút |
| `trends_trend` | Тренд | Trend | 趋势 | Xu hướng |
| **Экран «Анализ»** | | | | |
| `analysis_bt_apnea` | Апноэ | Apnea | 呼吸暂停 | Ngừng thở |
| `analysis_bt_apneustic` | Апнейстическое | Apneustic | 长吸气式 | Thở ngưng mạnh |
| `analysis_bt_biot` | Биота | Biot's | 比奥式 | Thở Biot |
| `analysis_bt_bradypnea` | Брадипноэ | Bradypnea | 呼吸缓慢 | Thở chậm |
| `analysis_bt_cheyne` | Чейна-Стокса | Cheyne-Stokes | 陈-施式 | Cheyne-Stokes |
| `analysis_bt_dyspnea` | Диспноэ | Dyspnea | 呼吸困难 | Khó thở |
| `analysis_bt_eupnea` | Эупноэ | Eupnea | 正常呼吸 | Thở bình thường |
| `analysis_bt_gasping` | Гаспинг | Gasping | 喘息 | Thở hổn hển |
| `analysis_bt_periodic` | Периодическое дыхание | Periodic breathing | 周期性呼吸 | Thở tuần hoàn |
| `analysis_bt_restrictive` | Дыхание с рестрикцией | Restrictive breathing | 限制性呼吸 | Thở hạn chế |
| `analysis_bt_tachypnea` | Тахипноэ | Tachypnea | 呼吸急促 | Thở nhanh |
| `analysis_current_type` | Текущий тип дыхания | Current breathing type | 当前呼吸类型 | Loại thở hiện tại |
| `analysis_possible_types` | Возможные типы дыхания | Possible breathing types | 可能的呼吸类型 | Các loại thở có thể |
| `analysis_sub_avg` | Усредн. графики аэрации | Averaged aeration charts | 平均通气图 | Biểu đồ thông khí TB |
| `analysis_sub_pca` | Анализ PCA | PCA Analysis | PCA分析 | Phân tích PCA |
| `analysis_tab_global` | Аэрация ГЛОБАЛЬНАЯ | GLOBAL Aeration | 全局 通气 | Thông khí TOÀN THỂ |
| `analysis_tab_pathology` | Тип патологического дыхания | Pathological Breathing Type | 病理呼吸类型 | Loại thở bệnh lý |
| `analysis_tab_regional` | Аэрация РЕГИОНАРНАЯ | REGIONAL Aeration | 区域 通气 | Thông khí KHU VỰC |
| **Экран «Настройки ЭИТ»** | | | | |
| `eit_belts_label` | Количество электродных поясов | Number of electrode belts | 电极带数 | Số vòng điện cực |
| `eit_btn_reset` | Сбросить настройки | Reset settings | 重置设置 | Đặt lại cài đặt |
| `eit_btn_save` | Сохранить настройки ЭИТ-исследования | Save EIT study settings | 保存EIT研究 设置 | Lưu cài đặt nghiên cứu EIT |
| `eit_current_label` | Сила инжектируемого тока | Injected current amplitude | 注入电流强度 | Cường độ dòng tiêm |
| `eit_current_placeholder` | Сила тока | Current | 电流 | Dòng điện |
| `eit_electrodes_label` | Количество электродов | Number of electrodes | 电极数量 | Số điện cực |
| `eit_freq_label` | Частота инжектируемого тока | Injected current frequency | 注入电流频率 | Tần số dòng tiêm |
| `eit_freq_placeholder` | Частота | Frequency | 频率 | Tần số |
| `eit_pathology_label` | Идентификация и отображение типа патологического дыхания | Identification and display of pathological breathing type | 病理呼吸类型 识别与显示 | Nhận dạng và hiển thị loại thở bệnh lý |
| `eit_unit_khz` | кГц | kHz | 千赫 | kHz |
| `eit_unit_ma` | мА | mA | 毫安 | mA |
| `eit_unit_pcs` | шт | pcs | 个 | cái |
| `eit_viz_2colors` | 2 цвета | 2 colours | 2色 | 2 màu |
| `eit_viz_color_label` | Задание цвета динамической визуализации дыхательного цикла | Colour mode of breathing cycle dynamic visualisation | 呼吸周期动态 可视化颜色设置 | Màu sắc hình ảnh động của chu kỳ thở |
| `eit_viz_standard` | Стандартное | Standard | 标准 | Tiêu chuẩn |
| **Экран «Экспорт данных»** | | | | |
| `exp_btn_details` | Подробнее | Details | 详情 | Chi tiết |
| `exp_btn_generate` | Сформировать | Generate | 生成 | Tạo |
| `exp_btn_reset` | Сбросить настройки | Reset settings | 重置设置 | Đặt lại cài đặt |
| `exp_format_title` | Формат экспорта | Export format | 导出格式 | Định dạng xuất |
| `exp_history_title` | История исследований | Study history | 检查历史 | Lịch sử nghiên cứu |
| `exp_prev_study` | Предыдущее исследование ЭИТ | Previous EIT study | 上次EIT检查 | Nghiên cứu EIT trước |
| **Экран «Отчёты»** | | | | |
| `rep_btn_generate` | Сформировать отчёт | Generate report | 生成报告 | Tạo báo cáo |
| `rep_btn_print` | Печать | Print | 打印 | In |
| `rep_btn_reset` | Сбросить параметры | Reset parameters | 重置参数 | Đặt lại thông số |
| `rep_btn_view` | Просмотр | View | 查看 | Xem |
| `rep_conclusion` | ЗАКЛЮЧЕНИЕ | CONCLUSION | 结论 | KẾT LUẬN |
| `rep_create_new` | Сформировать новый отчёт | Create new report | 创建新报告 | Tạo báo cáo mới |
| `rep_eit_study` | Исследование ЭИТ | EIT Study | EIT检查 | Nghiên cứu EIT |
| `rep_indicators` | Набор показателей | Indicator set | 指标集 | Bộ chỉ số |
| `rep_indicators_section` | ПОКАЗАТЕЛИ ВЕНТИЛЯЦИИ | VENTILATION INDICATORS | 通气指标 | CHỈ SỐ THÔNG KHÍ |
| `rep_new_btn` | + Новый отчёт | + New report | + 新报告 | + Báo cáo mới |
| `rep_patient` | Пациент | Patient | 患者 | Bệnh nhân |
| `rep_period` | Период | Period | 时间段 | Khoảng thời gian |
| `rep_period_from` | С | From | 从 | Từ |
| `rep_period_to` | По | To | 至 | Đến |
| `rep_preview_empty` | Выберите отчёт из списка или сформируйте новый | Select a report from the list or create a new one | 从列表中选择报告 或创建新报告 | Chọn báo cáo từ danh sách hoặc tạo báo cáo mới |
| `rep_preview_title` | Предварительный просмотр | Preview | 预览 | Xem trước |
| `rep_report_name` | Наименование отчёта | Report name | 报告名称 | Tên báo cáo |
| `rep_saved_reports` | Сохранённые отчёты | Saved reports | 已保存报告 | Báo cáo đã lưu |
| **Экран «Служебная информация»** | | | | |
| `svc_btn_add` | + Добавить событие | + Add event | + 添加事件 | + Thêm sự kiện |
| `svc_btn_reset_filter` | Сбросить | Reset | 重置 | Đặt lại |
| `svc_col_datetime` | Дата / Время | Date / Time | 日期 / 时间 | Ngày / Giờ |
| `svc_col_desc` | Описание | Description | 描述 | Mô tả |
| `svc_col_num` | № | # | 序 | STT |
| `svc_col_type` | Тип | Type | 类型 | Loại |
| `svc_dlg_cancel` | Отмена | Cancel | 取消 | Hủy |
| `svc_dlg_datetime` | Дата и время: | Date and time: | 日期和时间: | Ngày và giờ: |
| `svc_dlg_desc` | Описание: | Description: | 描述: | Mô tả: |
| `svc_dlg_desc_hint` | Введите описание события... | Enter event description... | 请输入事件描述... | Nhập mô tả sự kiện... |
| `svc_dlg_save` | Сохранить | Save | 保存 | Lưu |
| `svc_dlg_title` | Добавить событие | Add event | 添加事件 | Thêm sự kiện |
| `svc_dlg_type` | Тип события: | Event type: | 事件类型: | Loại sự kiện: |
| `svc_filter_all` | Все типы | All types | 所有类型 | Tất cả loại |
| `svc_filter_type` | Фильтр по типу: | Filter by type: | 按类型筛选: | Lọc theo loại: |
| `svc_no_events` | Нет зарегистрированных событий | No events recorded | 暂无记录事件 | Không có sự kiện nào |
| `svc_session_label` | Протокол событий текущего сеанса | Current session event log | 当前会话事件记录 | Nhật ký sự kiện phiên hiện tại |
| `svc_type_adverse_event` | Неблагоприятное событие | Adverse event | 不良事件 | Sự kiện bất lợi |
| `svc_type_adverse_phenom` | Неблагоприятное явление | Adverse phenomenon | 不良现象 | Hiện tượng bất lợi |
| `svc_type_operator_note` | Замечание оператора | Operator note | 操作员备注 | Ghi chú của thao tác viên |
| `svc_type_tech_error` | Техническая ошибка | Technical error | 技术故障 | Lỗi kỹ thuật |
| **Экран «Качество сигнала»** | | | | |
| `sq_btn_calibrate` | Калибровка | Calibrate | 校准 | Hiệu chỉnh |
| `sq_lbl_es_duration` | Длительность использования ЭС | Electrode system usage time | 电极系统使用时间 | Thời gian sử dụng hệ điện cực |
| `sq_lbl_monitor_duration` | Длительность мониторинга | Monitoring duration | 监测持续时间 | Thời gian giám sát |
| `sq_quality_adequate` | Адекватный | Adequate | 适中 | Phù hợp |
| `sq_quality_insufficient` | Недостаточно | Insufficient | 不足 | Không đủ |
| `sq_quality_strong` | Сильный | Strong | 强 | Mạnh |
| `sq_quality_tech_error` | Техническая ошибка | Technical error | 技术故障 | Lỗi kỹ thuật |
| `sq_quality_weak` | Слабый | Weak | 弱 | Yếu |
| **Экран «Системная информация»** | | | | |
| `sys_device_id` | ID устройства: | Device ID: | 设备ID: | ID thiết bị: |
| `sys_lang_change_btn` | Изменить язык | Change language | 更改语言 | Thay đổi ngôn ngữ |
| `sys_lang_current` | Текущий язык: | Current language: | 当前语言: | Ngôn ngữ hiện tại: |
| `sys_lang_section` | Язык интерфейса | Interface language | 界面语言 | Ngôn ngữ giao diện |
| `sys_lbl_battery` | Заряд АКБ | Battery charge | 电池电量 | Mức pin |
| `sys_lbl_belts` | Количество электродных поясов | Number of electrode belts | 电极带数 | Số vòng điện cực |
| `sys_lbl_current` | Сила инжектируемого тока | Injected current amplitude | 注入电流强度 | Cường độ dòng tiêm |
| `sys_lbl_datetime` | Дата и время | Date and time | 日期和时间 | Ngày và giờ |
| `sys_lbl_device_model` | Модель устройства ЭИТ | EIT device model | EIT设备型号 | Mô hình thiết bị EIT |
| `sys_lbl_electrodes` | Количество электродов | Number of electrodes | 电极数量 | Số điện cực |
| `sys_lbl_freq` | Частота инжектируемого тока | Injected current frequency | 注入电流频率 | Tần số dòng tiêm |
| `sys_lbl_language` | Язык интерфейса | Interface language | 界面语言 | Ngôn ngữ giao diện |
| `sys_lbl_release_date` | Дата выпуска | Release date | 发布日期 | Ngày phát hành |
| `sys_lbl_serial` | Серийный номер | Serial number | 序列号 | Số sê-ri |
| `sys_lbl_sw_name` | Наименование ПО | Software name | 软件名称 | Tên phần mềm |
| `sys_lbl_version` | Версия ПО | Software version | 软件版本 | Phiên bản phần mềm |
| `sys_tbl_num` | № п/п | # | 序号 | STT |
| `sys_tbl_param` | Параметр | Parameter | 参数 | Thông số |
| `sys_tbl_value` | Формат данных | Data format | 数据格式 | Định dạng dữ liệu |
| `sys_val_current` | 0,5 до 5 мА ± 10% | 0.5 to 5 mA ± 10% | 0.5至5 mA ± 10% | 0,5 đến 5 mA ± 10% |
| `sys_val_freq` | от 10 до 500 кГц ± 10% | 10 to 500 kHz ± 10% | 10至500 kHz ± 10% | 10 đến 500 kHz ± 10% |
| `sys_val_sw_name` | Прототип системы ЭИТ | EIT System Prototype | EIT系统原型 | Nguyên mẫu hệ thống EIT |
| `sys_version` | Версия ПО: | Software version: | 软件版本: | Phiên bản phần mềm: |
| **Диалог выбора языка** | | | | |
| `dlg_lang_cancel` | Отмена | Cancel | 取消 | Hủy |
| `dlg_lang_confirm` | Применить | Apply | 应用 | Áp dụng |
| `dlg_lang_title` | Выбор языка интерфейса | Select interface language | 选择界面语言 | Chọn ngôn ngữ giao diện |

---

## Термины технического задания

Термины из ТЗ (п. 5–8), для которых в интерфейсе уже есть переводы в `STRINGS`.
Источник терминов: `../eit_project_4_monitoring/docs/tech_task.md`.

| Термин (RU) | Русский | English | 中文 | Tiếng Việt | Ключ |
|---|---|---|---|---|---|
| ЭИТ | ЭИТ | EIT | EIT | EIT | `screen_eit_settings` |
| Электроимпедансная томография | электроимпедансной томографии | Electrical impedance tomography | 电阻抗断层扫描 | chụp cắt lớp điện trở | `sub_eit_settings` |
| ЭС (электродная система) | ЭС | ES | 电极系统 | hệ điện cực | `sq_lbl_es_duration` |
| ПО (программное обеспечение) | ПО | Software | 软件 | phần mềm | `sys_lbl_sw_name` |
| Монитор пациента | Монитор пациента | Patient Monitor | 患者监护仪 | Màn hình bệnh nhân | `app_title` |
| Пациент | Пациент | Patient | 患者 | Bệnh nhân | `screen_patient` |
| Глобальная аэрация | Глобальная аэрация | Global aeration | 全局通气 | Thông khí toàn thể | `wave_t_label` |
| Регионарная аэрация | Аэрация РЕГИОНАРНАЯ | REGIONAL Aeration | 区域通气 | Thông khí KHU VỰC | `analysis_tab_regional` |
| GLOBAL (глобальная) | GLOBAL | GLOBAL | 全局 | TOÀN THỂ | `trends_global_label` |
| REG (регионарная) | REG | REG | 区域 | KHU VỰC | `trends_reg_label` |
| Тренд | Тренд | Trend | 趋势 | Xu hướng | `wave_trend` |
| Тренды | Тренды | Trends | 趋势 | Xu hướng | `screen_trends` |
| Дыхательный цикл | Дыхательный цикл | Breathing cycle | 呼吸周期 | Chu kỳ thở | `lung_breath_cycle` |
| Визуализация дыхательного цикла | динамической визуализации дыхательного цикла | breathing cycle dynamic visualisation | 呼吸周期动态可视化 | hình ảnh động của chu kỳ thở | `eit_viz_color_label` |
| Частота дыхания | вд/мин | br/min | 次/分 | lần/phút | `wave_rr_unit` |
| Тип дыхания | тип дыхания | breathing type | 呼吸类型 | loại thở | `analysis_current_type` |
| Патологическое дыхание | Тип патологического дыхания | Pathological Breathing Type | 病理呼吸类型 | Loại thở bệnh lý | `analysis_tab_pathology` |
| Эупноэ | Эупноэ | Eupnea | 正常呼吸 | Thở bình thường | `analysis_bt_eupnea` |
| Тахипноэ | Тахипноэ | Tachypnea | 呼吸急促 | Thở nhanh | `analysis_bt_tachypnea` |
| Брадипноэ | Брадипноэ | Bradypnea | 呼吸缓慢 | Thở chậm | `analysis_bt_bradypnea` |
| Апноэ | Апноэ | Apnea | 呼吸暂停 | Ngừng thở | `analysis_bt_apnea` |
| Вентиляция | ПОКАЗАТЕЛИ ВЕНТИЛЯЦИИ | VENTILATION INDICATORS | 通气指标 | CHỈ SỐ THÔNG KHÍ | `rep_indicators_section` |
| Параметры вентиляции | параметров вентиляции | ventilation parameter | 通气参数 | thông số thông khí | `sub_analysis` |
| Левое лёгкое | Левое лёгкое | Left lung | 左肺 | Phổi trái | `wave_l_label` |
| Правое лёгкое | Правое лёгкое | Right lung | 右肺 | Phổi phải | `wave_r_label` |
| Мониторинг | мониторинга | Monitoring | 监测 | giám sát | `sq_lbl_monitor_duration` |
| Длительность мониторинга | Длительность мониторинга | Monitoring duration | 监测持续时间 | Thời gian giám sát | `sq_lbl_monitor_duration` |
| Длительность использования ЭС | Длительность использования ЭС | Electrode system usage time | 电极系统使用时间 | Thời gian sử dụng hệ điện cực | `sq_lbl_es_duration` |
| Исследование ЭИТ | Исследование ЭИТ | EIT Study | EIT检查 | Nghiên cứu EIT | `rep_eit_study` |
| ИВЛ | ИВЛ | Mechanical ventilation | 机械通气 | Thở máy | `pat_ivl` |
| Маркер событий | Маркер событий | Event marker | 事件标记 | Đánh dấu sự kiện | `trends_btn_marker` |
| Сигнал тревоги | СИГНАЛ ТРЕВОГИ | ALARM | 警报 | BÁO ĐỘNG | `hdr_alarm` |
| Неблагоприятное событие | Неблагоприятное событие | Adverse event | 不良事件 | Sự kiện bất lợi | `svc_type_adverse_event` |
| Неблагоприятное явление | Неблагоприятное явление | Adverse phenomenon | 不良现象 | Hiện tượng bất lợi | `svc_type_adverse_phenom` |
| ΔZ (изменение импеданса) | ΔZ,% | ΔZ,% | ΔZ,% | ΔZ,% | `trends_dz` |
| Электрод | электродов | electrodes | 电极 | điện cực | `eit_electrodes_label` |
| Электродный пояс | электродных поясов | electrode belts | 电极带 | vòng điện cực | `eit_belts_label` |
| Прототип системы ЭИТ | Прототип системы ЭИТ | EIT System Prototype | EIT系统原型 | Nguyên mẫu hệ thống EIT | `sys_val_sw_name` |
