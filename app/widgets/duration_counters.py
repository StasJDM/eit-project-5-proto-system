"""Счётчики «Длительность ЭИТ» и «Время использ. ЭС» — общий виджет."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout
from PySide6.QtCore import Qt

from ..styles import C, FONT_LABEL, FONT_VALUE, FONT_SMALL
from ..i18n import t, i18n

# Крупные счётчики для 12″ дисплея (вертикальные пары на главном / анализе)
_LABEL_FONT = FONT_LABEL + 12   # ~30 px
_VALUE_FONT = FONT_VALUE + 12   # ~36 px

# Компактная горизонтальная панель (отладка / качество сигнала)
_BAR_LABEL_FONT = round(FONT_SMALL * 1.75)   # ~28 px (+75 %)
_BAR_VALUE_FONT = FONT_VALUE                 # 24 px


class DurationCounter(QWidget):
    """Строка: метка и значение HH:MM:SS (горизонтально или вертикально)."""

    def __init__(
        self,
        label_key: str,
        stacked: bool = False,
        large: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._label_key = label_key
        self._stacked = stacked

        if stacked:
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 2, 0, 2)
            lay.setSpacing(2)
            label_font = FONT_LABEL + (6 if large else 0)
            value_font = FONT_VALUE + (8 if large else 0)
        else:
            lay = QHBoxLayout(self)
            lay.setContentsMargins(0, 2, 0, 2)
            lay.setSpacing(8)
            label_font = _LABEL_FONT
            value_font = _VALUE_FONT

        self._lbl = QLabel(t(label_key))
        self._lbl.setWordWrap(stacked)
        if stacked:
            self._lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._lbl.setStyleSheet(
            f"color:{C['text_dim']};font-size:{label_font}px;background:transparent;"
        )

        self._val = QLabel("00:00:00")
        if stacked:
            self._val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._val.setStyleSheet(
            f"color:{C['text']};font-size:{value_font}px;"
            f"font-family:monospace;font-weight:bold;background:transparent;"
        )

        lay.addWidget(self._lbl)
        lay.addWidget(self._val)
        if not stacked:
            lay.addStretch()

        i18n.language_changed.connect(self.retranslate)

    def set_value(self, text: str):
        self._val.setText(text)

    def retranslate(self):
        self._lbl.setText(t(self._label_key))


class DurationCounterPair(QWidget):
    """Два счётчика, расположенные вертикально или рядом друг с другом."""

    def __init__(
        self,
        stacked: bool = False,
        large: bool = False,
        horizontal: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        lay = QHBoxLayout(self) if horizontal else QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(24 if horizontal else 4)

        self.cnt_eit = DurationCounter("param_eit_duration", stacked=stacked, large=large)
        self.cnt_es = DurationCounter("param_es_time", stacked=stacked, large=large)
        lay.addWidget(self.cnt_eit)
        lay.addWidget(self.cnt_es)

    def set_values(self, eit: str, es: str):
        self.cnt_eit.set_value(eit)
        self.cnt_es.set_value(es)

    def retranslate(self):
        self.cnt_eit.retranslate()
        self.cnt_es.retranslate()


class DurationCounterBar(QWidget):
    """Горизонтальная панель с двумя счётчиками (экраны отладки / качества сигнала)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(24)

        mon_block, self._lbl_mon, self._val_mon = self._make_counter_block(
            "sq_lbl_monitor_duration",
        )
        lay.addWidget(mon_block)

        lay.addStretch()

        es_block, self._lbl_es, self._val_es = self._make_counter_block(
            "sq_lbl_es_duration",
        )
        lay.addWidget(es_block)

        i18n.language_changed.connect(self.retranslate)

    def _make_counter_block(self, label_key: str):
        block = QWidget()
        block.setStyleSheet("background:transparent;")
        vlay = QVBoxLayout(block)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(4)

        lbl = QLabel(t(label_key))
        lbl.setStyleSheet(
            f"color:{C['text_dim']};font-size:{_BAR_LABEL_FONT}px;background:transparent;"
        )

        val = QLabel("00:00:00")
        val.setStyleSheet(self._boxed_style())

        vlay.addWidget(lbl)
        vlay.addWidget(val, alignment=Qt.AlignLeft)
        return block, lbl, val

    @staticmethod
    def _boxed_style() -> str:
        return (
            f"color:{C['text']};font-size:{_BAR_VALUE_FONT}px;font-weight:bold;"
            f"font-family:monospace;background:{C['bg_card']};"
            f"border:1px solid {C['border']};padding:6px 16px;border-radius:4px;"
        )

    def set_values(self, eit: str, es: str):
        self._val_mon.setText(eit)
        self._val_es.setText(es)

    def retranslate(self):
        self._lbl_mon.setText(t("sq_lbl_monitor_duration"))
        self._lbl_es.setText(t("sq_lbl_es_duration"))
