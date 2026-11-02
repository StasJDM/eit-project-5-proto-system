# Примеры входных измерений ЭИТ

Все JSON-файлы в каталоге проходят строгий контракт приложения: один пояс,
16 электродов, 208 числовых каналов в кадре и последовательная нумерация.
Межпроектные дубли исключены по содержимому.

| Файл | Кадры | Источник | Назначение |
|---|---:|---|---|
| `2x_circle_r0.15_20260608_211810.json` | 1 | project 3, `2x_circle_r0.15_20260608_211810/output.json` | Два круглых объекта; файл по умолчанию |
| `project3_single_circle_r0.20_1_frame.json` | 1 | project 3, `1x_circle_r0.20_20260608_211758/output.json` | Один круглый объект |
| `project3_homogeneous_5_frames.json` | 5 | project 3, `homogeneous_20260609_124635/output.json` | Однородный фантом |
| `project2_single_object_5_frames.json` | 5 | project 2, `examples/actual/1object_greit/single_object.json` | Синтетический одиночный объект |
| `project2_double_object_d02_5_frames.json` | 5 | project 2, `examples/version_3/block_2/double_object_gauss_newton/double_object_d02.json` | Синтетические два объекта |
| `project1_demo_3_frames.json` | 3 | project 1, `input_data/demo_data.json` | Короткий демонстрационный набор |
| `project6_400khz_6_frames.json` | 6 | project 6, `json_26_6.json` из серии «Данные_30.03» | Короткая аппаратная запись, 400 кГц и 5 мА |
| `eupnea.json` | 300 | project 4, `examples/eupnea.json` | Динамическая запись спокойного дыхания, 25 Гц |

Статические и короткие файлы в стартовом режиме `fromfile` воспроизводятся
циклически. Файлы из проектов 1–3 не содержат отдельного baseline, поэтому их
time-difference реконструкция не является абсолютным изображением объекта.

Пример запуска выбранного набора:

```bash
EIT_FROMFILE_PATH=examples/fromfile/project6_400khz_6_frames.json python3 main.py
```
