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
| `hdr_live` | ЭФИР | LIVE | 实时 | TRỰC TIẾP |
| `hdr_menu_tooltip` | Главное меню | Main Menu | 主菜单 | Menu chính |
| `hdr_playback` | АРХИВ | REPLAY | 回放 | PHÁT LẠI |
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
| `lung_reconstruction_map` | Карта реконструкции ΔZ | Reconstructed ΔZ map | 重建 ΔZ 图 | Bản đồ tái tạo ΔZ |
| `lung_reconstruction_tooltip` | Каждая ячейка соответствует одному элементу реконструкции | Each cell represents one reconstruction element | 每个单元格对应一个重建元素 | Mỗi ô tương ứng với một phần tử tái tạo |
| **Панель кривых (WaveformPanel)** | | | | |
| `wave_event_marker` | ⚑  МАРКЕР СОБЫТИЙ | ⚑  EVENT MARKER | ⚑  事件标记 | ⚑  ĐÁNH DẤU SỰ KIỆN |
| `wave_l_label` | L  Левое лёгкое | L  Left lung | L  左肺 | L  Phổi trái |
| `wave_r_label` | R  Правое лёгкое | R  Right lung | R  右肺 | R  Phổi phải |
| `wave_rr_unit` | вд/мин | br/min | 次/分 | lần/phút |
| `wave_rr_short` | ЧД | RR | 呼吸率 | NT |
| `wave_t_label` | T  Глобальная аэрация | T  Global aeration | T  全局通气 | T  Thông khí toàn thể |
| `wave_trend` | Тренд | Trend | 趋势 | Xu hướng |
| **Левая панель / общие кнопки** | | | | |
| `btn_start` | ▶  СТАРТ | ▶  START | ▶  开始 | ▶  BẮT ĐẦU |
| `btn_stop` | ⏹  СТОП | ⏹  STOP | ⏹  停止 | ⏹  DỪNG |
| `study_stop_title` | Завершение исследования | Complete study | 结束检查 | Kết thúc nghiên cứu |
| `study_stop_confirm` | Завершить активное исследование? После завершения оно будет доступно только для просмотра и экспорта. | Complete the active study? Afterwards it will be available only for viewing and export. | 结束当前检查？结束后只能查看和导出。 | Kết thúc nghiên cứu đang hoạt động? Sau đó chỉ có thể xem và xuất. |
| `study_action_error_title` | Действие недоступно | Action unavailable | 操作不可用 | Thao tác không khả dụng |
| `study_prepare_first` | Сначала сохраните пациента и привяжите новое исследование. | Save the patient and link a new study first. | 请先保存患者并关联新的检查。 | Trước tiên hãy lưu bệnh nhân và liên kết nghiên cứu mới. |
| `study_invalid_transition` | Переход в это состояние исследования недопустим. | This study state transition is not allowed. | 不允许转换到此检查状态。 | Không cho phép chuyển sang trạng thái nghiên cứu này. |
| `study_contact_quality_blocked` | Старт запрещён: исправьте критически плохой контакт электродов. | Start blocked: correct critically poor electrode contact. | 无法开始：请修复严重不良的电极接触。 | Đã chặn bắt đầu: khắc phục tiếp xúc điện cực quá kém. |
| `study_playback_unavailable` | Запись исследования недоступна или повреждена. | The study recording is unavailable or damaged. | 检查记录不可用或已损坏。 | Bản ghi nghiên cứu không khả dụng hoặc bị hỏng. |
| `study_select_patient_first` | Сначала сохраните или выберите пациента. | Save or select a patient first. | 请先保存或选择患者。 | Trước tiên hãy lưu hoặc chọn bệnh nhân. |
| `study_finish_current_first` | Сначала завершите текущее исследование. | Complete the current study first. | 请先结束当前检查。 | Hãy kết thúc nghiên cứu hiện tại trước. |
| `study_active_other_patient` | Нельзя сменить пациента во время активного исследования. | The patient cannot be changed during an active study. | 活动检查期间不能更换患者。 | Không thể đổi bệnh nhân trong khi nghiên cứu đang hoạt động. |
| `study_linked_title` | Исследование подготовлено | Study prepared | 检查已准备 | Nghiên cứu đã sẵn sàng |
| `study_linked_message` | Новое исследование привязано к выбранному пациенту и готово к запуску. | A new study is linked to the selected patient and ready to start. | 新检查已关联到所选患者，可以开始。 | Nghiên cứu mới đã được liên kết với bệnh nhân và sẵn sàng bắt đầu. |
| `study_status_draft` | Черновик | Draft | 草稿 | Bản nháp |
| `study_status_ready` | Готово | Ready | 就绪 | Sẵn sàng |
| `study_status_running` | Выполняется | Running | 进行中 | Đang chạy |
| `study_status_paused` | Приостановлено | Paused | 已暂停 | Tạm dừng |
| `study_status_completed` | Завершено | Completed | 已完成 | Hoàn thành |
| `study_status_failed` | Завершено аварийно | Failed | 异常结束 | Thất bại |
| `study_conclusion_missing` | Заключение не указано | No conclusion provided | 未提供结论 | Chưa có kết luận |
| `study_conclusion_emergency` | Аварийное завершение | Emergency termination | 紧急终止 | Kết thúc khẩn cấp |
| `study_conclusion_restart` | Прервано перезапуском приложения | Interrupted by application restart | 因应用重启而中断 | Bị gián đoạn do khởi động lại ứng dụng |
| `study_conclusion_application_closed` | Завершено при закрытии приложения | Completed when the application was closed | 应用关闭时结束 | Hoàn tất khi đóng ứng dụng |
| `study_details_title` | Исследование ЭИТ | EIT study | EIT 检查 | Nghiên cứu EIT |
| `study_details_date` | Дата | Date | 日期 | Ngày |
| `study_details_duration` | Длительность | Duration | 时长 | Thời lượng |
| `study_details_status` | Статус | Status | 状态 | Trạng thái |
| `study_details_conclusion` | Заключение | Conclusion | 结论 | Kết luận |
| `study_details_author` | Автор | Author | 作者 | Tác giả |
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
| `pat_icd_code` | МКБ | ICD | ICD | ICD |
| `pat_icd_code_10` | МКБ-10 | ICD-10 | ICD-10 | ICD-10 |
| `pat_icd_code_11` | МКБ-11 | ICD-11 | ICD-11 | ICD-11 |
| `pat_id` | ID | ID | ID | ID |
| `pat_ivl` | ИВЛ | Mechanical ventilation | 机械通气 | Thở máy |
| `pat_last_name` | Фамилия | Last name | 姓 | Họ |
| `pat_link_study` | Привязать текущее исследование к выбранному пациенту | Link current study to selected patient | 将当前检查与 所选患者关联 | Liên kết nghiên cứu hiện tại với bệnh nhân đã chọn |
| `pat_history_empty` | У выбранного пациента пока нет исследований | The selected patient has no studies yet | 所选患者尚无检查记录 | Bệnh nhân đã chọn chưa có nghiên cứu |
| `pat_icd_dialog_title` | Выбор диагноза | Select diagnosis | 选择诊断 | Chọn chẩn đoán |
| `pat_icd_search` | Поиск по коду или названию | Search by code or title | 按代码或名称搜索 | Tìm theo mã hoặc tên |
| `pat_invalid_diagnosis` | Выберите диагноз из активного справочника МКБ | Select a diagnosis from the active ICD catalogue | 请从当前 ICD 目录中选择诊断 | Chọn chẩn đoán từ danh mục ICD đang hoạt động |
| `pat_ivl_dialog_title` | Параметры ИВЛ | Ventilation parameters | 机械通气参数 | Thông số thở máy |
| `pat_ivl_mode` | Режим | Mode | 模式 | Chế độ |
| `pat_ivl_fio2` | FiO₂ | FiO₂ | FiO₂ | FiO₂ |
| `pat_ivl_peep` | ПДКВ | PEEP | PEEP | PEEP |
| `pat_unsaved_title` | Несохранённые изменения | Unsaved changes | 未保存的更改 | Thay đổi chưa lưu |
| `pat_unsaved_message` | Закрыть карточку и отбросить несохранённые изменения? | Close the card and discard unsaved changes? | 关闭病历并放弃未保存的更改？ | Đóng hồ sơ và bỏ các thay đổi chưa lưu? |
| `pat_unsaved_discard` | Не сохранять | Don't save | 不保存 | Không lưu |
| `pat_unsaved_cancel` | Отмена | Cancel | 取消 | Hủy |
| `pat_validation_title` | Проверьте данные | Check the data | 检查数据 | Kiểm tra dữ liệu |
| `pat_validation_message` | Заполните обязательные поля корректными уникальными значениями. | Fill in required fields with valid unique values. | 请使用有效且唯一的值填写必填字段。 | Điền các trường bắt buộc bằng giá trị hợp lệ và duy nhất. |
| `pat_error_required` | Обязательное поле. | This field is required. | 此字段为必填项。 | Trường này là bắt buộc. |
| `pat_error_name_format` | Используйте имя без цифр. | Use a name without digits. | 姓名中不能包含数字。 | Tên không được chứa chữ số. |
| `pat_error_birth_future` | Дата рождения не может быть в будущем. | The date of birth cannot be in the future. | 出生日期不能晚于今天。 | Ngày sinh không thể ở tương lai. |
| `pat_error_id_format` | Введите от 3 до 32 латинских букв, цифр или символов . _ - | Enter 3–32 Latin letters, digits, or . _ - | 请输入 3–32 个拉丁字母、数字或 . _ - | Nhập 3–32 chữ cái Latinh, chữ số hoặc . _ - |
| `pat_error_duplicate` | Такое значение уже используется. | This value is already in use. | 该值已被使用。 | Giá trị này đã được sử dụng. |
| `pat_error_record_format` | Введите номер истории болезни (до 64 символов). | Enter a medical record number (up to 64 characters). | 请输入病历号（最多 64 个字符）。 | Nhập số hồ sơ bệnh án (tối đa 64 ký tự). |
| `pat_error_weight_range` | Введите массу от 0,5 до 500 кг. | Enter a weight from 0.5 to 500 kg. | 请输入 0.5 至 500 千克的体重。 | Nhập cân nặng từ 0,5 đến 500 kg. |
| `pat_error_height_range` | Введите рост от 20 до 250 см. | Enter a height from 20 to 250 cm. | 请输入 20 至 250 厘米的身高。 | Nhập chiều cao từ 20 đến 250 cm. |
| `pat_error_chest_range` | Введите охват грудной клетки от 20 до 250 см. | Enter a chest circumference from 20 to 250 cm. | 请输入 20 至 250 厘米的胸围。 | Nhập vòng ngực từ 20 đến 250 cm. |
| `pat_error_invalid_value` | Проверьте значение поля. | Check this field value. | 请检查该字段的值。 | Kiểm tra giá trị của trường này. |
| `pat_saved_title` | Карточка сохранена | Card saved | 病历已保存 | Đã lưu hồ sơ |
| `pat_saved_message` | Данные пациента сохранены. | Patient data has been saved. | 患者数据已保存。 | Đã lưu dữ liệu bệnh nhân. |
| `pat_load_dicom` | Загрузить снимок DICOM | Load DICOM image | 加载DICOM图像 | Tải ảnh DICOM |
| `pat_lung_morph` | Морфология лёгких (определить границы) | Lung morphology (define boundaries) | 肺形态学 (确定边界) | Hình thái phổi (xác định ranh giới) |
| `pat_main_diag` | Диагноз основной | Main diagnosis | 主要诊断 | Chẩn đoán chính |
| `pat_save_card` | Сохранить карточку | Save card | 保存档案 | Lưu hồ sơ |
| `pat_no` | Нет | No | 否 | Không |
| `pat_patronymic` | Отчество | Patronymic | 父名 | Tên đệm |
| `pat_personal_title` | Персонализация | Personalization | 个性化 | Cá nhân hóa |
| `pat_prev_study` | Предыдущее исследование ЭИТ | Previous EIT study | 上次EIT检查 | Nghiên cứu EIT trước |
| `pat_preview` | Предварительный просмотр | Preview | 预览 | Xem trước |
| `pat_playback` | Просмотр | Playback | 回放 | Phát lại |
| `pat_import_eit_json` | Загрузить измерения ЭИТ из JSON | Load EIT measurements from JSON | 从 JSON 加载 EIT 测量 | Tải phép đo EIT từ JSON |
| `pat_import_eit_json_hint` | Исследовательская FEM/GREIT-реконструкция; порядок каналов и геометрия требуют подтверждения | Research FEM/GREIT reconstruction; channel order and geometry require confirmation | 研究性 FEM/GREIT 重建；通道顺序和几何形状需要确认 | Tái tạo FEM/GREIT nghiên cứu; thứ tự kênh và hình học cần được xác nhận |
| `pat_import_eit_json_filter` | Измерения ЭИТ JSON (*.json) | EIT JSON measurements (*.json) | EIT JSON 测量 (*.json) | Phép đo EIT JSON (*.json) |
| `pat_import_eit_json_error` | Файл не удалось проверить или реконструировать. Требуются последовательные кадры по 208 числовых каналов. | The file could not be validated or reconstructed. Sequential frames with 208 numeric channels are required. | 无法验证或重建文件。需要包含 208 个数值通道的连续帧。 | Không thể xác thực hoặc tái tạo tệp. Cần các khung liên tiếp với 208 kênh số. |
| `pat_record_num` | Номер истории болезни | Medical record № | 病历号 | Số hồ sơ bệnh án |
| **Воспроизведение исследования** | | | | |
| `playback_read_only` | АРХИВ · только просмотр | ARCHIVE · read only | 存档 · 只读 | LƯU TRỮ · chỉ đọc |
| `playback_pause` | Пауза | Pause | 暂停 | Tạm dừng |
| `playback_resume` | Продолжить | Resume | 继续 | Tiếp tục |
| `playback_close` | Закрыть | Close | 关闭 | Đóng |
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
| `trends_time` | Время | Time | 时间 | Thời gian |
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
| `eit_diagnosis_catalog_label` | Справочник диагнозов | Diagnosis catalogue | 诊断目录 | Danh mục chẩn đoán |
| `eit_icd10` | МКБ-10 | ICD-10 | ICD-10 | ICD-10 |
| `eit_icd11` | МКБ-11 | ICD-11 | ICD-11 | ICD-11 |
| `eit_unit_khz` | кГц | kHz | 千赫 | kHz |
| `eit_unit_ma` | мА | mA | 毫安 | mA |
| `eit_unit_pcs` | шт | pcs | 个 | cái |
| `eit_color_map_label` | Цветовая карта | Colour map | 色彩映射 | Bản đồ màu |
| `eit_custom_color_low` | Цвет 1 | Colour 1 | 颜色 1 | Màu 1 |
| `eit_custom_color_high` | Цвет 2 | Colour 2 | 颜色 2 | Màu 2 |
| `eit_custom_color` | Цвет | Colour | 颜色 | Màu |
| `eit_viz_1color` | 1 цвет | 1 colour | 1色 | 1 màu |
| `eit_viz_2colors` | 2 цвета | 2 colours | 2色 | 2 màu |
| `eit_viz_color_label` | Задание цвета динамической визуализации дыхательного цикла | Colour mode of breathing cycle dynamic visualisation | 呼吸周期动态 可视化颜色设置 | Màu sắc hình ảnh động của chu kỳ thở |
| `eit_viz_standard` | Стандартное | Standard | 标准 | Tiêu chuẩn |
| `color_map_medical_blue_amber` | Медицинская: синий — янтарный | Medical: blue — amber | 医疗：蓝色—琥珀色 | Y khoa: xanh lam — hổ phách |
| `color_map_blue_red` | Синий — красный | Blue — red | 蓝色—红色 | Xanh lam — đỏ |
| `color_map_cyan_orange` | Голубой — оранжевый | Cyan — orange | 青色—橙色 | Lục lam — cam |
| `color_map_teal_coral` | Бирюзовый — коралловый | Teal — coral | 蓝绿色—珊瑚色 | Xanh ngọc — san hô |
| `color_map_indigo_yellow` | Индиго — жёлтый | Indigo — yellow | 靛蓝—黄色 | Chàm — vàng |
| `color_map_purple_lime` | Фиолетовый — лайм | Purple — lime | 紫色—青柠色 | Tím — chanh |
| `color_map_green_magenta` | Зелёный — маджента | Green — magenta | 绿色—品红色 | Xanh lá — đỏ tía |
| `color_map_navy_gold` | Тёмно-синий — золотой | Navy — gold | 海军蓝—金色 | Xanh hải quân — vàng kim |
| `color_map_ice_fire` | Лёд — пламя | Ice — fire | 冰—火 | Băng — lửa |
| `color_map_emerald_violet` | Изумрудный — фиолетовый | Emerald — violet | 祖母绿—紫罗兰 | Lục bảo — tím |
| `color_map_sky_rose` | Небесный — розовый | Sky — rose | 天蓝—玫红 | Da trời — hồng |
| `color_map_mint_ruby` | Мятный — рубиновый | Mint — ruby | 薄荷色—红宝石色 | Bạc hà — hồng ngọc |
| `color_map_azure_tangerine` | Лазурный — мандариновый | Azure — tangerine | 天蓝—橘色 | Xanh da trời — quýt |
| `color_map_turquoise_pink` | Бирюзовый — розовый | Turquoise — pink | 绿松石色—粉色 | Ngọc lam — hồng |
| `color_map_monochrome` | Монохромная | Monochrome | 单色 | Đơn sắc |
| `color_map_custom` | Пользовательская | Custom | 自定义 | Tùy chỉnh |
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
| `svc_all_studies_label` | Протокол событий всех исследований | All studies event log | 所有检查事件记录 | Nhật ký sự kiện của tất cả nghiên cứu |
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
| `svc_filter_period` | Период: | Period: | 时间范围: | Khoảng thời gian: |
| `svc_filter_to` | — | to | 至 | đến |
| `svc_filter_type` | Фильтр по типу: | Filter by type: | 按类型筛选: | Lọc theo loại: |
| `svc_no_events` | Нет зарегистрированных событий | No events recorded | 暂无记录事件 | Không có sự kiện nào |
| `svc_scope_all` | Все исследования | All studies | 所有检查 | Tất cả nghiên cứu |
| `svc_scope_current` | Текущее исследование | Current study | 当前检查 | Nghiên cứu hiện tại |
| `svc_session_label` | Протокол событий текущего сеанса | Current session event log | 当前会话事件记录 | Nhật ký sự kiện phiên hiện tại |
| `svc_study_ref` | Исследование | Study | 检查 | Nghiên cứu |
| `svc_type_adverse_event` | Неблагоприятное событие | Adverse event | 不良事件 | Sự kiện bất lợi |
| `svc_type_adverse_phenom` | Неблагоприятное явление | Adverse phenomenon | 不良现象 | Hiện tượng bất lợi |
| `svc_type_operator_note` | Замечание оператора | Operator note | 操作员备注 | Ghi chú của thao tác viên |
| `svc_type_tech_error` | Техническая ошибка | Technical error | 技术故障 | Lỗi kỹ thuật |
| **Экран «Качество сигнала»** | | | | |
| `sq_btn_calibrate` | Калибровка | Calibrate | 校准 | Hiệu chỉnh |
| `sq_calibration_failed` | Калибровка отклонена: проверьте электроды {electrodes} | Calibration failed: check electrodes {electrodes} | 校准失败：请检查电极 {electrodes} | Hiệu chỉnh thất bại: kiểm tra điện cực {electrodes} |
| `sq_calibration_no_study` | Сначала подготовьте исследование пациента | Prepare a patient study before calibration | 请先准备患者检查 | Hãy chuẩn bị nghiên cứu bệnh nhân trước khi hiệu chỉnh |
| `sq_calibration_running` | Выполняется калибровка… | Calibration in progress… | 正在校准… | Đang hiệu chỉnh… |
| `sq_calibration_success` | Калибровка завершена и сохранена в исследовании | Calibration completed and saved in the study | 校准完成并已保存到检查中 | Hiệu chỉnh hoàn tất và đã lưu vào nghiên cứu |
| `sq_lbl_es_duration` | Длительность использования ЭС | Electrode system usage time | 电极系统使用时间 | Thời gian sử dụng hệ điện cực |
| `sq_lbl_monitor_duration` | Длительность мониторинга | Monitoring duration | 监测持续时间 | Thời gian giám sát |
| `sq_quality_adequate` | Адекватный | Adequate | 适中 | Phù hợp |
| `sq_quality_insufficient` | Недостаточно | Insufficient | 不足 | Không đủ |
| `sq_quality_strong` | Сильный | Strong | 强 | Mạnh |
| `sq_quality_tech_error` | Техническая ошибка | Technical error | 技术故障 | Lỗi kỹ thuật |
| `sq_quality_weak` | Слабый | Weak | 弱 | Yếu |
| `sq_status_blocked` | Пригодных измерений: {percent}% · старт заблокирован | Usable measurements: {percent}% · start blocked | 可用测量：{percent}% · 已阻止开始 | Phép đo sử dụng được: {percent}% · đã chặn bắt đầu |
| `sq_status_ready` | Пригодных измерений: {percent}% · старт разрешён | Usable measurements: {percent}% · start allowed | 可用测量：{percent}% · 允许开始 | Phép đo sử dụng được: {percent}% · được phép bắt đầu |
| `sq_status_waiting` | Ожидание данных диагностики электродов | Waiting for electrode diagnostics | 正在等待电极诊断数据 | Đang chờ dữ liệu chẩn đoán điện cực |
| **Экран «Системная информация»** | | | | |
| `sys_device_id` | ID устройства: | Device ID: | 设备ID: | ID thiết bị: |
| `sys_element_main_mvi` | Отображать MVi | Show MVi | 显示 MVi | Hiển thị MVi |
| `sys_engineering_graph_period` | Период отображения данных на графиках: | Data display period on charts: | 图表数据的显示时段： | Khoảng thời gian hiển thị dữ liệu trên biểu đồ: |
| `sys_engineering_graph_period_value` | {seconds} с | {seconds} s | {seconds} 秒 | {seconds} giây |
| `sys_engineering_tab_trends` | Тренды | Trends | 趋势 | Xu hướng |
| `sys_engineering_trend_point_mode` | Источник точек тренда: | Trend point source: | 趋势点来源： | Nguồn điểm xu hướng: |
| `sys_trend_points_interval` | Интервалы 15 с (TB) | 15-second intervals (TB) | 15 秒间隔 (TB) | Khoảng 15 giây (TB) |
| `sys_trend_points_breath_cycle` | Завершённые дыхательные циклы (BB) | Completed breath cycles (BB) | 完整呼吸周期 (BB) | Chu kỳ thở hoàn chỉnh (BB) |
| `sys_engineering_trend_downsampling` | Укрупнение длинных диапазонов: | Long-range aggregation: | 长范围聚合： | Tổng hợp phạm vi dài: |
| `sys_trend_downsampling_none` | Без укрупнения | No aggregation | 不聚合 | Không tổng hợp |
| `sys_trend_downsampling_adult` | Медиана по руководству — взрослые | Manual median — adult | 手册中位数 — 成人 | Trung vị theo hướng dẫn — người lớn |
| `sys_trend_downsampling_infant` | Медиана по руководству — новорождённые | Manual median — neonatal | 手册中位数 — 新生儿 | Trung vị theo hướng dẫn — sơ sinh |
| `sys_engineering_trend_configuration_hint` | BB использует сохранённые точки завершённых циклов. TB использует 15-секундные агрегаты. Медианное укрупнение применяет коэффициенты руководства для выбранного диапазона времени. | BB uses persisted completed-cycle points. TB uses 15-second aggregates. Median aggregation applies the manual factors for the selected time range. | BB 使用保存的完整周期点。TB 使用 15 秒聚合。中位数聚合按所选时间范围应用手册系数。 | BB dùng các điểm chu kỳ hoàn chỉnh đã lưu. TB dùng tổng hợp 15 giây. Tổng hợp trung vị áp dụng hệ số hướng dẫn cho khoảng thời gian đã chọn. |
| `sys_element_main_velocity` | График скорости V = dZ/dt | Velocity chart V = dZ/dt | 速度图 V = dZ/dt | Biểu đồ vận tốc V = dZ/dt |
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
| `common_ok` | ОК | OK | 确定 | Đồng ý |
| `common_cancel` | Отмена | Cancel | 取消 | Hủy |
| `common_yes` | Да | Yes | 是 | Có |
| `common_no` | Нет | No | 否 | Không |
| `monitor_reason_unknown` | причина не определена | reason not specified | 原因未指定 | chưa xác định nguyên nhân |
| `ui_reason_label` | Причина | Reason | 原因 | Nguyên nhân |
| `ui_algorithm_version` | Версия алгоритма | Algorithm version | 算法版本 | Phiên bản thuật toán |
| `study_status_unknown` | Статус не определён | Unknown status | 状态未知 | Trạng thái không xác định |
| `study_conclusion_start_failed` | Не удалось начать мониторинг | Monitoring failed to start | 监测启动失败 | Không thể bắt đầu giám sát |
| `analysis_param_sample_rate` | Частота дискретизации | Sample rate | 采样率 | Tần số lấy mẫu |
| `analysis_param_smoothing` | Отсчётов сглаживания | Smoothing samples | 平滑样本数 | Số mẫu làm mượt |
| `analysis_param_min_cycles` | Минимум полных циклов | Minimum complete cycles | 最少完整周期 | Số chu kỳ hoàn chỉnh tối thiểu |
| `analysis_param_rr_range` | Диапазон ЧД | Respiratory-rate range | 呼吸频率范围 | Khoảng nhịp thở |
| `analysis_unit_hz` | Гц | Hz | 赫兹 | Hz |
| `sys_mode_simulation` | Симуляция | Simulation | 模拟 | Mô phỏng |
| `sys_mode_device` | Устройство | Device | 设备 | Thiết bị |
| `sys_mode_fromfile` | Из файла | From file | 来自文件 | Từ tệp |
| `sys_not_configured` | не настроено | not configured | 未配置 | chưa cấu hình |
| `svc_search_placeholder` | Поиск | Search | 搜索 | Tìm kiếm |
| `exp_category_metadata` | Метаданные и пациент | Metadata and patient | 元数据和患者 | Siêu dữ liệu và bệnh nhân |
| `exp_category_metrics` | Итоговые показатели | Summary metrics | 汇总指标 | Chỉ số tổng hợp |
| `exp_category_trends` | Тренды | Trends | 趋势 | Xu hướng |
| `exp_category_events` | События | Events | 事件 | Sự kiện |
| `exp_category_raw` | Сырые данные | Raw data | 原始数据 | Dữ liệu thô |
| `exp_privacy_warning` | Экспорт может содержать персональные данные. | The export may contain personal data. | 导出内容可能包含个人数据。 | Dữ liệu xuất có thể chứa thông tin cá nhân. |
| `exp_no_studies` | Нет сохранённых исследований | No saved studies | 没有已保存的检查 | Không có nghiên cứu đã lưu |
| `exp_estimate` | Выбрано исследований: {count}; оценка размера: {size} | Selected studies: {count}; estimated size: {size} | 已选检查：{count}；预计大小：{size} | Nghiên cứu đã chọn: {count}; dung lượng ước tính: {size} |
| `exp_detail_patient` | Пациент | Patient | 患者 | Bệnh nhân |
| `exp_detail_status` | Статус | Status | 状态 | Trạng thái |
| `exp_detail_created` | Создано | Created | 创建时间 | Đã tạo |
| `exp_detail_conclusion` | Заключение | Conclusion | 结论 | Kết luận |
| `exp_selection_error` | Выберите хотя бы одно исследование и категорию данных. | Select at least one study and one data category. | 请至少选择一项检查和一个数据类别。 | Chọn ít nhất một nghiên cứu và một loại dữ liệu. |
| `exp_generation_error` | Не удалось сформировать экспорт. Подробности записаны в технический журнал. | The export could not be generated. Details were written to the technical log. | 无法生成导出。详细信息已写入技术日志。 | Không thể tạo bản xuất. Chi tiết đã được ghi vào nhật ký kỹ thuật. |
| `exp_saved` | Экспорт сохранён: {path} | Export saved: {path} | 导出已保存：{path} | Đã lưu bản xuất: {path} |
| `rep_default_title` | Отчёт ЭИТ | EIT report | EIT 报告 | Báo cáo EIT |
| `rep_generation_error` | Не удалось сформировать отчёт. Проверьте выбранное исследование и период. | The report could not be generated. Check the selected study and period. | 无法生成报告。请检查所选检查和时间段。 | Không thể tạo báo cáo. Hãy kiểm tra nghiên cứu và khoảng thời gian đã chọn. |
| `rep_preview_error` | Не удалось открыть предварительный просмотр отчёта. | The report preview could not be opened. | 无法打开报告预览。 | Không thể mở bản xem trước báo cáo. |
| `rep_print_error` | Не удалось напечатать отчёт. | The report could not be printed. | 无法打印报告。 | Không thể in báo cáo. |
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
| Качество данных | Данные: качество в норме | Data quality: valid | 数据质量：正常 | Chất lượng dữ liệu: hợp lệ | `monitor_quality_valid` |
| Низкое качество данных | Данные: низкое качество | Data quality: degraded | 数据质量：较低 | Chất lượng dữ liệu: suy giảm | `monitor_quality_degraded` |
| Гипотезы реконструкции | FEM/GREIT-реконструкция рассчитана, но порядок каналов и геометрия прибора не подтверждены | FEM/GREIT reconstruction is calculated, but device channel order and geometry are unconfirmed | FEM/GREIT 重建已计算，但设备通道顺序和几何形状尚未确认 | Đã tính tái tạo FEM/GREIT, nhưng thứ tự kênh và hình học thiết bị chưa được xác nhận | `monitor_reason_reconstruction_hypothesis` |
| Обновление приостановлено | Данные: обновление приостановлено | Data: updates paused | 数据：更新已暂停 | Dữ liệu: cập nhật đã tạm dừng | `monitor_quality_stale` |
| Данные недоступны | Данные недоступны | Data unavailable | 数据不可用 | Dữ liệu không khả dụng | `monitor_quality_unavailable` |
| Маркер события | Маркер события | Event marker | 事件标记 | Đánh dấu sự kiện | `marker_dialog_title` |
| Позиция исследования | Позиция исследования | Study position | 检查位置 | Vị trí nghiên cứu | `marker_position` |
| Корректирующая запись | Корректирующая запись | Correction entry | 更正记录 | Bản ghi hiệu chỉnh | `marker_correction_title` |
