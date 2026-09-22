"""Verileri Hesapla: the queue between recording and labelling.

Two lists, **side by side**: the takes with no finished version yet on the
left, the attempts that are running or have finished on the right. Stacked, as
they were until 19 September, each list got half the height of a screen that is
mostly width - eight rows visible out of forty, with the right-hand two thirds
of every row empty. Vertical is the scarce direction on this screen and
horizontal is the plentiful one, so the split follows the window rather than
fighting it.

Everything a job reports comes from its own ``job.json``: the stage, the frame
count, the rate, and a percentage **only** where the source declared a total.
Where it did not, the bar is indeterminate and says so - there is no honest
denominator to divide by and inventing one would be the most misleading thing
this screen could do.

"İptal ham kaydı silmez" is printed next to the button, not hidden in a
confirmation nobody reads twice.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from kinecapture.dataset.summary_index import TakeSummary
from kinecapture.studio.services.formatting import duration, local_datetime, timezone_note
from kinecapture.studio.services.processing import Job, JobState
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.navigation import Destination
from kinecapture.studio.viewmodels.processing import CANCEL_NOTE, ProcessingViewModel

from .. import iconset
from ..models import (
    ROW_ROLE,
    Column,
    RowTableModel,
    SearchProxy,
    configure_columns,
)
from ..widgets import ElidedLabel, label, mono_label, separator
from .base import StudioPage

#: Job files are re-read at this rate. Progress that updates faster than it can
#: be read costs paint time and tells nobody anything.
_POLL_INTERVAL_MS = 400

_STATE_TEXT = {
    JobState.QUEUED: "sırada",
    JobState.RUNNING: "işleniyor",
    JobState.PAUSED: "duraklatıldı",
    JobState.COMPLETE: "tamamlandı",
    JobState.PARTIAL: "kapsam doğrulanamadı",
    JobState.FAILED: "başarısız",
    JobState.CANCELLED: "iptal edildi",
}

_STATE_STATUS = {
    JobState.COMPLETE: "live",
    JobState.PARTIAL: "warning",
    JobState.FAILED: "error",
    JobState.CANCELLED: "warning",
}


def _waiting_columns() -> tuple[Column[TakeSummary], ...]:
    return (
        Column(
            "participant",
            "Katılımcı",
            lambda r: r.participant_id,
            tooltip=lambda r: r.take_id,
        ),
        Column(
            "started",
            "Tarih",
            lambda r: local_datetime(r.started_at),
            sort_key=lambda r: r.started_at,
            tooltip=lambda r: timezone_note(r.started_at),
            numeric=True,
        ),
        Column(
            "duration",
            "Süre",
            lambda r: duration(r.duration_s),
            sort_key=lambda r: r.duration_s,
            numeric=True,
        ),
        Column(
            "frames", "Kare", lambda r: str(r.frames), sort_key=lambda r: r.frames, numeric=True
        ),
        Column(
            "attempts",
            "Deneme",
            lambda r: str(len(r.runs)) if r.runs else "—",
            sort_key=lambda r: len(r.runs),
            numeric=True,
        ),
    )


def _job_columns() -> tuple[Column[Job], ...]:
    return (
        Column(
            "take",
            "Kayıt",
            lambda j: f"{j.take.participant_id} · {local_datetime(j.take.started_at)}",
            tooltip=lambda j: j.take.take_id,
            stretch=True,
        ),
        Column(
            "state",
            "Durum",
            lambda j: _STATE_TEXT.get(j.progress.state, j.progress.state.value),
            status=lambda j: _STATE_STATUS.get(j.progress.state, ""),
        ),
        Column("progress", "İlerleme", lambda j: j.progress.progress_text, numeric=True),
        Column("eta", "Kalan", lambda j: j.progress.eta_text, numeric=True),
        Column(
            "rate",
            "Hız",
            lambda j: (f"{j.progress.rate_fps:.1f} FPS" if j.progress.rate_fps else "—"),
            numeric=True,
        ),
        Column(
            "issues",
            "Bulgular",
            lambda j: " · ".join(j.progress.issue_texts) or "—",
            tooltip=lambda j: "\n".join(j.progress.issue_texts) or "Bulgu yok",
        ),
    )


class ProcessingPage(StudioPage):
    def __init__(
        self,
        destination: Destination,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(destination, tokens, parent)
        self.viewmodel: Optional[ProcessingViewModel] = None

        self.summary = ElidedLabel("")
        self.summary.setProperty("kcRole", "sectionTitle")

        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.setProperty("kcVariant", "quiet")
        self.refresh_button.setIcon(
            iconset.icon("refresh", tokens, size=tokens.metric("KcIconSize"))
        )
        self.add_header_action(self.refresh_button)

        # Two columns, not two stacked bands. The starting split is the
        # approved 40/60: the source list only has to be scannable, while the
        # queue carries stage, progress, rate and time-remaining per row.
        self.split = QSplitter(Qt.Orientation.Horizontal, self)
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(self._build_sources(tokens))
        self.split.addWidget(self._build_queue(tokens))
        self.split.setStretchFactor(0, 4)
        self.split.setStretchFactor(1, 6)
        self.body_layout.addWidget(self.split, 1)
        # The approved starting ratio, held through resizes until the user
        # takes hold of the handle. Stretch factors alone only divide the
        # *spare* room, which on a wide window left the split wherever the two
        # size hints happened to put it - measured at 33/67, not 40/60.
        self._split_pinned = True
        self.split.splitterMoved.connect(
            lambda *_: setattr(self, "_split_pinned", False)
        )

        self.start_button.clicked.connect(self._start_selected)
        self.start_all_button.clicked.connect(self._start_all)
        self.refresh_button.clicked.connect(self._refresh)
        self.pause_button.clicked.connect(self._pause_selected)
        self.resume_button.clicked.connect(self._resume_selected)
        self.cancel_button.clicked.connect(self._cancel_selected)
        self.retry_button.clicked.connect(self._retry_selected)
        self.job_view.selectionModel().selectionChanged.connect(self._job_selected)
        self.waiting_view.selectionModel().selectionChanged.connect(
            self._take_selected
        )

        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------- the panels
    def _build_sources(self, tokens: ThemeTokens) -> QWidget:
        """Left: what is waiting, how to find it, and what would be applied."""
        panel = QWidget(self)
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, tokens.metric("KcSpacingMd"), 0)
        column.setSpacing(tokens.metric("KcSpacingMd"))

        # Everything above the table goes in one widget, and everything below
        # it in another. The two columns then match their heads and their
        # feet to each other (see :meth:`_align_bands`), so the two tables -
        # which are what the eye reads as "the two containers" - start and end
        # on exactly the same two lines. Without this the left head carried a
        # search row the right head did not, and the tables were 46 px out at
        # the top and 63 px out at the bottom.
        head = QWidget(panel)
        head_column = QVBoxLayout(head)
        head_column.setContentsMargins(0, 0, 0, 0)
        head_column.setSpacing(tokens.metric("KcSpacingMd"))
        column.addWidget(head)

        head_column.addWidget(label("İŞLENMEYİ BEKLEYENLER", role="sectionTitle"))
        head_column.addWidget(self.summary)

        # Search and a participant filter, because forty takes from one
        # session all look alike in a list sorted by date.
        finder = QHBoxLayout()
        finder.setSpacing(tokens.metric("KcSpacingSm"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Katılımcı veya tarih ara")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Bekleyen kayıtlarda ara")
        finder.addWidget(self.search, 1)
        self.participant_box = QComboBox()
        self.participant_box.setAccessibleName("Katılımcı filtresi")
        self.participant_box.setToolTip("Listeyi tek bir katılımcıya daraltır")
        self.participant_box.addItem("Tüm katılımcılar", "")
        finder.addWidget(self.participant_box)
        for control in (self.search, self.participant_box):
            control.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        head_column.addLayout(finder)
        self.sources_head = head

        self.waiting_model, self.waiting_view = self._make_table(
            _waiting_columns(), "İşlenmeyi bekleyen kayıtlar"
        )
        # More than one at a time: queueing a session's worth of takes is the
        # normal thing to do here, and doing it one row at a time is not.
        self.waiting_view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.waiting_proxy = SearchProxy(self)
        self.waiting_proxy.setSourceModel(self.waiting_model)
        self.waiting_view.setModel(self.waiting_proxy)
        self.waiting_view.setSortingEnabled(True)
        column.addWidget(self.waiting_view, 1)

        self.search.textChanged.connect(self.waiting_proxy.set_search)
        self.participant_box.currentIndexChanged.connect(self._participant_chosen)

        foot = QWidget(panel)
        foot_column = QVBoxLayout(foot)
        foot_column.setContentsMargins(0, 0, 0, 0)
        foot_column.setSpacing(tokens.metric("KcSpacingMd"))
        column.addWidget(foot)
        self.sources_foot = foot

        # An open take is not a queue entry. Said here so its absence from the
        # list above reads as a decision rather than as a missing recording.
        self.open_note = ElidedLabel("")
        self.open_note.setProperty("kcStatus", "warning")
        self.open_note.hide()
        foot_column.addWidget(self.open_note)

        # What the selected take is, and what would be applied to it. One
        # block, so "işle" is never pressed without seeing both.
        foot_column.addWidget(separator())
        self.selection_summary = QLabel("Bir kayıt seçin.")
        self.selection_summary.setWordWrap(True)
        self.selection_summary.setProperty("kcRole", "pageSubtitle")
        foot_column.addWidget(self.selection_summary)

        profile_row = QHBoxLayout()
        profile_row.setSpacing(tokens.metric("KcSpacingSm"))
        profile_row.addWidget(label("ETKİN PROFİL", role="sectionTitle"))
        self.profile_label = ElidedLabel("")
        self.profile_label.setProperty("kcRole", "pageSubtitle")
        profile_row.addWidget(self.profile_label, 1)
        self.profile_button = QPushButton("Ayrıntılar")
        self.profile_button.setProperty("kcVariant", "quiet")
        self.profile_button.setCheckable(True)
        self.profile_button.setIcon(
            iconset.icon("expand", tokens, size=tokens.metric("KcIconSize"))
        )
        self.profile_button.toggled.connect(self._toggle_profile)
        profile_row.addWidget(self.profile_button)
        foot_column.addLayout(profile_row)
        # The long technical list stays folded away: it is wanted exactly when
        # something looks wrong, and never while choosing what to queue.
        self.profile_detail = QLabel("")
        self.profile_detail.setProperty("kcRole", "mono")
        self.profile_detail.setWordWrap(True)
        self.profile_detail.hide()
        foot_column.addWidget(self.profile_detail)

        actions = QHBoxLayout()
        actions.setSpacing(tokens.metric("KcSpacingMd"))
        self.start_button = QPushButton("Seçileni işle")
        self.start_button.setProperty("kcVariant", "primary")
        self.start_all_button = QPushButton("Hepsini kuyruğa al")
        for button in (self.start_button, self.start_all_button):
            button.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        actions.addWidget(self.start_button)
        actions.addWidget(self.start_all_button)
        actions.addStretch(1)
        foot_column.addLayout(actions)
        return panel

    def _build_queue(self, tokens: ThemeTokens) -> QWidget:
        """Right: the queue, its counts, and what can be done to one job."""
        panel = QWidget(self)
        column = QVBoxLayout(panel)
        column.setContentsMargins(tokens.metric("KcSpacingMd"), 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingMd"))

        head = QWidget(panel)
        head_column = QVBoxLayout(head)
        head_column.setContentsMargins(0, 0, 0, 0)
        head_column.setSpacing(tokens.metric("KcSpacingMd"))
        column.addWidget(head)
        self.queue_head = head

        head_column.addWidget(label("İŞ KUYRUĞU", role="sectionTitle"))

        # Four counts, always in the same four places, so a glance answers
        # "is anything stuck?" without reading the table.
        counts = QHBoxLayout()
        counts.setSpacing(tokens.metric("KcSpacingXl"))
        self.counts: dict[str, QLabel] = {}
        for key, caption in (
            ("queued", "Sırada"),
            ("running", "Çalışıyor"),
            ("done", "Tamamlandı"),
            ("failed", "Sorunlu"),
        ):
            pair = QHBoxLayout()
            pair.setSpacing(tokens.metric("KcSpacingSm"))
            pair.addWidget(label(caption, role="contextKey"))
            value = mono_label("0")
            self.counts[key] = value
            pair.addWidget(value)
            counts.addLayout(pair)
        counts.addStretch(1)
        head_column.addLayout(counts)

        self.job_model, self.job_view = self._make_table(_job_columns(), "İşler")
        column.addWidget(self.job_view, 1)

        foot = QWidget(panel)
        foot_column = QVBoxLayout(foot)
        foot_column.setContentsMargins(0, 0, 0, 0)
        foot_column.setSpacing(tokens.metric("KcSpacingMd"))
        column.addWidget(foot)
        self.queue_foot = foot

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        # Room kept whether or not a job is running. Hiding it gave the height
        # back, which moved the four buttons under it - and, now that the two
        # columns are matched foot to foot, would have moved the other
        # column's table with them.
        self.progress.setMinimumHeight(tokens.metric("KcControlHeight"))
        self.progress.hide()
        foot_column.addWidget(self.progress)

        job_actions = QHBoxLayout()
        job_actions.setSpacing(tokens.metric("KcSpacingMd"))
        self.pause_button = QPushButton("Duraklat")
        self.pause_button.setToolTip(
            "Seçili işi olduğu yerde tutar. Yapılan iş korunur."
        )
        self.resume_button = QPushButton("Devam et")
        self.resume_button.setToolTip("Duraklatılan işi kaldığı yerden sürdürür.")
        self.cancel_button = QPushButton("İptal")
        self.cancel_button.setToolTip(CANCEL_NOTE)
        self.retry_button = QPushButton("Yeniden dene")
        self.retry_button.setToolTip(
            "Biten ya da başarısız olan işi baştan çalıştırır. Önceki deneme "
            "olduğu gibi kalır."
        )
        for button in (
            self.pause_button,
            self.resume_button,
            self.cancel_button,
            self.retry_button,
        ):
            # Not "quiet": beside a table of real rows these read as captions
            # rather than as controls, which is half of why the user reported
            # them as not working at all.
            button.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
            button.setEnabled(False)
            job_actions.addWidget(button)
        job_actions.addStretch(1)
        foot_column.addLayout(job_actions)
        self.cancel_note = ElidedLabel(CANCEL_NOTE)
        self.cancel_note.setProperty("kcRole", "pageSubtitle")
        self.cancel_note.setToolTip(CANCEL_NOTE)
        foot_column.addWidget(self.cancel_note)
        #: Why the four buttons are as they are, in words. An action that is
        #: off has to say what would turn it on; a greyed button with no
        #: sentence is indistinguishable from a broken one.
        self.action_note = ElidedLabel("")
        self.action_note.setProperty("kcRole", "pageSubtitle")
        foot_column.addWidget(self.action_note)
        return panel

    def _make_table(self, columns, caption: str):  # noqa: ANN001
        model = RowTableModel(columns, self)
        view = QTableView(self)
        view.setModel(model)
        view.setAlternatingRowColors(True)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.verticalHeader().setVisible(False)
        view.setWordWrap(False)
        view.setTextElideMode(Qt.TextElideMode.ElideRight)
        configure_columns(view, columns, fill=False)
        view.setAccessibleName(caption)
        return model, view

    # -------------------------------------------------------------- binding
    def attach(self, viewmodel: ProcessingViewModel) -> None:
        self.viewmodel = viewmodel
        self.bind(viewmodel.waiting, self._show_waiting)
        self.bind(viewmodel.open_takes, self._show_open_takes)
        self.bind(viewmodel.jobs, self._show_jobs)
        self.bind(viewmodel.summary, self.summary.setText)
        self.bind(viewmodel.busy, self._show_busy)
        self.bind(viewmodel.can_pause, self._show_pause_support)
        self.bind(viewmodel.profile_summary, self.profile_label.setText)
        self.bind(viewmodel.profile_rows, self._show_profile_rows)
        self.bind_event(viewmodel.message, self.show_message)

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().resizeEvent(event)
        self._apply_split_ratio()
        self._align_bands()

    def showEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().showEvent(event)
        self._align_bands()

    def _align_bands(self) -> None:
        """Make the two columns' heads and feet the same height as each other.

        The 21 September review asks for the two containers to start and end
        on the same two lines. Their contents are genuinely different - the
        left one needs a search row and a profile block, the right one needs
        four counts and four buttons - so the answer is not to make them hold
        the same things but to give each band the height of the taller of the
        pair. Whatever is left over goes to the tables, which take the
        stretch, and the tables therefore agree to the pixel.

        Re-run on every resize because a wrapped label changes a band's
        requested height with the window's width.
        """
        for left, right in (
            (self.sources_head, self.queue_head),
            (self.sources_foot, self.queue_foot),
        ):
            wanted = max(
                left.sizeHint().height(),
                right.sizeHint().height(),
                left.minimumSizeHint().height(),
                right.minimumSizeHint().height(),
            )
            for band in (left, right):
                if band.minimumHeight() != wanted or band.maximumHeight() != wanted:
                    band.setFixedHeight(wanted)

    #: The source list's share at rest. The queue carries stage, progress,
    #: rate and time-remaining per row and needs the wider half.
    SOURCE_SHARE = 0.4

    def _apply_split_ratio(self) -> None:
        """Hold the 40/60 split through resizes, until the user overrides it."""
        if not self._split_pinned:
            return
        width = self.split.width()
        if width <= 0:
            return
        wanted = int(width * self.SOURCE_SHARE)
        sizes = self.split.sizes()
        if sizes and abs(sizes[0] - wanted) <= 1:
            return
        self.split.setSizes([wanted, width - wanted])

    def page_activated(self) -> None:
        self._apply_split_ratio()
        if self.viewmodel is None:
            return
        self.viewmodel.refresh_profile()
        self.viewmodel.reload()
        self._timer.start()

    def page_deactivated(self) -> None:
        self._timer.stop()

    # ----------------------------------------------------------------- slots
    def _tick(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.poll()

    def _show_busy(self, busy: bool) -> None:
        self.refresh_button.setEnabled(not busy)

    def _show_open_takes(self, takes: tuple[TakeSummary, ...]) -> None:
        if not takes:
            self.open_note.hide()
            return
        names = ", ".join(take.take_id for take in takes)
        self.open_note.setText(
            f"{len(takes)} kayıt hâlâ açık ve listede yok: {names}. "
            "Kayıt kapanınca işlenmeye uygun olur."
        )
        self.open_note.show()

    def _toggle_profile(self, shown: bool) -> None:
        self.profile_detail.setVisible(shown)

    def _show_profile_rows(self, rows: tuple[tuple[str, str], ...]) -> None:
        self.profile_detail.setText(
            "\n".join(f"{name:<20}{value}" for name, value in rows)
        )
        # The one-line summary is part of what the selection block says, so it
        # is repeated there whenever the profile changes under it.
        self._take_selected()

    def _show_pause_support(self, supported: bool) -> None:
        self.pause_button.setToolTip(
            "" if supported else "Bu makinede duraklatma desteklenmiyor."
        )

    @staticmethod
    def _keep_selection(view, key_of):  # noqa: ANN001, ANN205
        """Re-select the same rows after the model behind ``view`` is reset.

        ``RowTableModel.set_rows`` resets the model, and a reset clears a
        view's selection. The queue is re-read four times a second, so a job
        somebody had clicked on stayed selected for at most 400 ms - after
        which ``_job_selected`` saw nothing selected and disabled Duraklat,
        Devam et, İptal and Yeniden dene again. That is the 21 September
        report that "the queue buttons do not work": they did work, for less
        time than it takes to move the pointer to them.

        Returns a callable that puts the selection back by *identity* rather
        than by row number, so a row that moved is still the row the user
        chose and a row that disappeared simply stays unselected.
        """
        model = view.selectionModel()
        wanted = {
            key_of(index.data(ROW_ROLE))
            for index in model.selectedRows()
            if index.data(ROW_ROLE) is not None
        }

        def restore() -> None:
            if not wanted:
                return
            source = view.model()
            selection = QItemSelection()
            for position in range(source.rowCount()):
                index = source.index(position, 0)
                row = index.data(ROW_ROLE)
                if row is not None and key_of(row) in wanted:
                    selection.select(index, source.index(position, source.columnCount() - 1))
            if not selection.isEmpty():
                model.select(
                    selection,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect
                    | QItemSelectionModel.SelectionFlag.Rows,
                )

        return restore

    def _show_waiting(self, takes: tuple[TakeSummary, ...]) -> None:
        """Fill the list, and keep the participant filter in step with it."""
        restore = self._keep_selection(self.waiting_view, lambda t: t.take_id)
        self.waiting_model.set_rows(takes)
        restore()
        wanted = sorted({take.participant_id for take in takes if take.participant_id})
        current = self.participant_box.currentData() or ""
        existing = [
            self.participant_box.itemData(i)
            for i in range(1, self.participant_box.count())
        ]
        if existing != wanted:
            # Rebuilt only when the set really changed, so typing in the search
            # box does not churn the combo three times a second.
            self.participant_box.blockSignals(True)
            self.participant_box.clear()
            self.participant_box.addItem("Tüm katılımcılar", "")
            for participant in wanted:
                self.participant_box.addItem(participant, participant)
            index = self.participant_box.findData(current)
            self.participant_box.setCurrentIndex(max(0, index))
            self.participant_box.blockSignals(False)
        self._apply_participant_filter()
        self._take_selected()

    def _participant_chosen(self, _index: int) -> None:
        self._apply_participant_filter()

    def _apply_participant_filter(self) -> None:
        """A filter, not a second search: the two narrow the list together."""
        wanted = self.participant_box.currentData() or ""
        self.waiting_proxy.set_required(wanted)

    def _take_selected(self, *_args) -> None:
        """What "Seçileni işle" would act on, said before it is pressed."""
        takes = self._selected_takes()
        self.start_button.setEnabled(bool(takes))
        if not takes:
            self.selection_summary.setText("Bir kayıt seçin.")
            return
        if len(takes) > 1:
            total = sum(take.duration_s for take in takes)
            people = sorted({t.participant_id for t in takes if t.participant_id})
            self.selection_summary.setText(
                f"{len(takes)} kayıt seçildi · toplam {duration(total)} · "
                + (", ".join(people) if people else "katılımcı yok")
            )
            return
        take = takes[0]
        attempts = len(take.runs)
        parts = [
            take.participant_id or "katılımcı yok",
            duration(take.duration_s),
            f"{take.frames} kare",
        ]
        if attempts:
            parts.append(f"{attempts} önceki deneme")
        self.selection_summary.setText(
            " · ".join(parts)
            + "\n"
            + (self.profile_label.text() or "işleme profili okunuyor…")
        )
        self.selection_summary.setToolTip(take.take_id)

    def _show_jobs(self, jobs: tuple[Job, ...]) -> None:
        restore = self._keep_selection(self.job_view, lambda j: j.key)
        self.job_model.set_rows(jobs)
        restore()
        # Four counts from the jobs themselves, so they cannot disagree with
        # the table beside them.
        tally = {"queued": 0, "running": 0, "done": 0, "failed": 0}
        for job in jobs:
            state = job.progress.state
            if state in (JobState.QUEUED, JobState.PAUSED):
                tally["queued"] += 1
            elif state is JobState.RUNNING:
                tally["running"] += 1
            elif state is JobState.COMPLETE:
                tally["done"] += 1
            else:
                # PARTIAL, FAILED and CANCELLED all want somebody to look.
                tally["failed"] += 1
        for key, value in tally.items():
            widget = self.counts[key]
            widget.setText(str(value))
            if key == "failed":
                widget.setProperty("kcStatus", "error" if value else None)
                style = widget.style()
                if style is not None:
                    style.unpolish(widget)
                    style.polish(widget)
        active = [j for j in jobs if j.progress.state is JobState.RUNNING]
        if not active:
            self.progress.hide()
        else:
            job = active[0]
            fraction = job.progress.fraction
            if fraction is None:
                # No declared total: a busy indicator, never a made-up number.
                self.progress.setRange(0, 0)
                self.progress.setFormat(job.progress.progress_text)
            else:
                self.progress.setRange(0, 100)
                self.progress.setValue(int(fraction * 100))
                self.progress.setFormat(
                    f"{job.progress.progress_text}  ·  %{int(fraction * 100)}"
                )
            self.progress.show()
        self._job_selected()

    def _selected_job(self) -> Optional[Job]:
        rows = self.job_view.selectionModel().selectedRows()
        return rows[0].data(ROW_ROLE) if rows else None

    def _selected_takes(self) -> list[TakeSummary]:
        """Every selected take, in the order the list shows them."""
        rows = self.waiting_view.selectionModel().selectedRows()
        found = [index.data(ROW_ROLE) for index in rows]
        return [take for take in found if take is not None]

    def _selected_take(self) -> Optional[TakeSummary]:
        takes = self._selected_takes()
        return takes[0] if takes else None

    def _job_selected(self, *_args) -> None:
        """Which of the four apply to the selected job, and why not the rest.

        Each answer is a state, not a guess: RUNNING can be paused and
        cancelled, PAUSED can be resumed and cancelled, QUEUED can be
        cancelled, and anything finished can be run again. A button that is
        off says what would turn it on, in :attr:`action_note` - the
        21 September report was partly that these four looked broken, and a
        greyed control with no sentence beside it is indistinguishable from
        one that is.
        """
        job = self._selected_job()
        state = job.progress.state if job else None
        running = state is JobState.RUNNING
        paused = state is JobState.PAUSED
        queued = state is JobState.QUEUED
        finished = bool(state and state.is_finished)
        can_pause = bool(self.viewmodel and self.viewmodel.can_pause.value)
        self.pause_button.setEnabled(running and can_pause)
        self.resume_button.setEnabled(paused)
        # A queued job holds a child process too, so it can be cancelled -
        # and cancelling one before it starts is the cheapest moment to.
        self.cancel_button.setEnabled(running or paused or queued)
        self.retry_button.setEnabled(finished)

        if job is None:
            note = "Bir iş seçin; eylemler seçili işe uygulanır."
        elif running:
            note = (
                "İş çalışıyor: duraklatılabilir veya iptal edilebilir."
                if can_pause
                else "İş çalışıyor: iptal edilebilir. Bu makinede duraklatma yok."
            )
        elif paused:
            note = "İş duraklatıldı: devam ettirilebilir veya iptal edilebilir."
        elif queued:
            note = "İş sırada: iptal edilebilir."
        elif finished:
            note = f"İş bitti ({_STATE_TEXT.get(state, '')}): yeniden denenebilir."
        else:
            note = ""
        self.action_note.setText(note)
        self.action_note.setToolTip(note)

    # --------------------------------------------------------------- actions
    def _refresh(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.reload(force=True)

    def _start_selected(self) -> None:
        """Queue every selected take, in list order. One press, one decision."""
        if self.viewmodel is None:
            return
        for take in self._selected_takes():
            self.viewmodel.start(take)

    def _start_all(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.start_all()

    def _pause_selected(self) -> None:
        job = self._selected_job()
        if job and self.viewmodel:
            self.viewmodel.pause(job.key)

    def _resume_selected(self) -> None:
        job = self._selected_job()
        if job and self.viewmodel:
            self.viewmodel.resume(job.key)

    def _cancel_selected(self) -> None:
        job = self._selected_job()
        if job and self.viewmodel:
            self.viewmodel.cancel(job.key)

    def _retry_selected(self) -> None:
        job = self._selected_job()
        if job and self.viewmodel:
            self.viewmodel.restart(job.take)


__all__ = ["ProcessingPage"]
