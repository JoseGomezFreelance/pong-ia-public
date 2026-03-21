"""Tests del sistema de logros (pong/achievements.py)."""
from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from pong.achievements import (
    ACHIEVEMENT_DEFS,
    ALL_ACHIEVEMENT_MOTIFS,
    ALL_ACHIEVEMENT_TIERS,
    ALL_CATEGORIES,
    ALL_MOOD_TAGS,
    CATEGORY_SECRET,
    AchievementDef,
    AchievementEngine,
    CareerStats,
    _CAREER_THRESHOLDS,
)


# ============================================================
# Helpers
# ============================================================

def _make_engine(**overrides: Any) -> AchievementEngine:
    """Crea un AchievementEngine con career_stats personalizados."""
    engine = AchievementEngine()
    for key, value in overrides.items():
        if hasattr(engine.career_stats, key):
            setattr(engine.career_stats, key, value)
    return engine


def _make_session(**overrides: Any) -> dict[str, Any]:
    """Crea un dict de session_data con valores por defecto."""
    session: dict[str, Any] = {
        "winner": "jugador",
        "player_sets": 1,
        "computer_sets": 0,
        "player_games": 2,
        "computer_games": 1,
        "player_points_total": 7,
        "computer_points_total": 5,
        "elapsed_seconds": 200.0,
        "max_rally": 12,
        "longest_player_streak": 3,
        "point_differential": 2,
        "llm_summary": "",
    }
    session.update(overrides)
    return session


def _make_point_result(**overrides: Any) -> SimpleNamespace:
    """Crea un PointResult minimo como SimpleNamespace."""
    result = SimpleNamespace(
        scorer_id="jugador",
        event_label="punto del jugador",
        last_play="El jugador gano el punto",
        scoring_streak=1,
        point_won=True,
        game_won=False,
        set_won=False,
        match_won=False,
    )
    for key, value in overrides.items():
        setattr(result, key, value)
    return result


def _make_score(**overrides: Any) -> SimpleNamespace:
    """Crea un ScoreState minimo como SimpleNamespace."""
    score = SimpleNamespace(
        player_points=0,
        computer_points=0,
        player_games=0,
        computer_games=0,
        player_sets=0,
        computer_sets=0,
    )
    for key, value in overrides.items():
        setattr(score, key, value)
    return score


def _make_context(**overrides: Any) -> dict[str, Any]:
    """Crea un context dict con valores por defecto para check_realtime."""
    ctx: dict[str, Any] = {
        "rally_hits": 0,
        "max_rally_hits": 0,
        "score": _make_score(),
        "point_result": _make_point_result(),
        "pre_player_pts": 0,
        "pre_computer_pts": 0,
        "mood_tag": "neutral",
        "elapsed_seconds": 60.0,
        "dialogue_history": [],
        "winner": "player",
    }
    ctx.update(overrides)
    return ctx


# ============================================================
# Tests de definiciones
# ============================================================

class AchievementDefTests(unittest.TestCase):
    """Tests de las definiciones estaticas de logros."""

    def test_all_ids_unique(self) -> None:
        """Todos los IDs deben ser unicos."""
        ids = list(ACHIEVEMENT_DEFS.keys())
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_have_required_fields(self) -> None:
        """Cada logro tiene name, description, flavor y metadatos visuales."""
        for aid, adef in ACHIEVEMENT_DEFS.items():
            with self.subTest(aid=aid):
                self.assertTrue(adef.name, f"{aid} sin nombre")
                self.assertTrue(adef.description, f"{aid} sin descripcion")
                self.assertTrue(adef.flavor, f"{aid} sin flavor")
                self.assertTrue(adef.tier, f"{aid} sin tier")
                self.assertTrue(adef.motif, f"{aid} sin motif")

    def test_category_is_valid(self) -> None:
        """Cada logro tiene una categoria valida."""
        for aid, adef in ACHIEVEMENT_DEFS.items():
            with self.subTest(aid=aid):
                self.assertIn(adef.category, ALL_CATEGORIES)

    def test_hidden_only_for_secrets(self) -> None:
        """Solo los logros secretos tienen hidden=True."""
        for aid, adef in ACHIEVEMENT_DEFS.items():
            with self.subTest(aid=aid):
                if adef.hidden:
                    self.assertEqual(adef.category, CATEGORY_SECRET)

    def test_total_achievement_count(self) -> None:
        """Hay exactamente 45 logros definidos."""
        self.assertEqual(len(ACHIEVEMENT_DEFS), 45)

    def test_tier_is_valid(self) -> None:
        """Cada logro usa un tier visual valido."""
        for aid, adef in ACHIEVEMENT_DEFS.items():
            with self.subTest(aid=aid):
                self.assertIn(adef.tier, ALL_ACHIEVEMENT_TIERS)

    def test_motif_is_valid(self) -> None:
        """Cada logro usa un motif visual valido."""
        for aid, adef in ACHIEVEMENT_DEFS.items():
            with self.subTest(aid=aid):
                self.assertIn(adef.motif, ALL_ACHIEVEMENT_MOTIFS)

    def test_icon_seed_is_non_negative_int(self) -> None:
        """Cada logro tiene icon_seed entero no negativo."""
        for aid, adef in ACHIEVEMENT_DEFS.items():
            with self.subTest(aid=aid):
                self.assertIsInstance(adef.icon_seed, int)
                self.assertGreaterEqual(adef.icon_seed, 0)


# ============================================================
# Tests de CareerStats
# ============================================================

class CareerStatsTests(unittest.TestCase):
    """Tests de calculo de estadisticas de carrera."""

    def test_recompute_empty_sessions(self) -> None:
        """Sesiones vacias producen stats a cero."""
        engine = AchievementEngine()
        stats = engine.recompute_career_stats([])
        self.assertEqual(stats.total_matches, 0)
        self.assertEqual(stats.total_victories, 0)
        self.assertEqual(stats.total_points_scored, 0)
        self.assertEqual(stats.total_rallies, 0)

    def test_recompute_single_win(self) -> None:
        """Una victoria incrementa todos los campos."""
        engine = AchievementEngine()
        session = _make_session(
            winner="jugador",
            player_points_total=7,
            max_rally=10,
        )
        stats = engine.recompute_career_stats([session])
        self.assertEqual(stats.total_matches, 1)
        self.assertEqual(stats.total_victories, 1)
        self.assertEqual(stats.total_points_scored, 7)
        self.assertEqual(stats.total_rallies, 10)

    def test_recompute_single_loss(self) -> None:
        """Una derrota incrementa partidos pero no victorias."""
        engine = AchievementEngine()
        session = _make_session(winner="ordenador", player_points_total=3)
        stats = engine.recompute_career_stats([session])
        self.assertEqual(stats.total_matches, 1)
        self.assertEqual(stats.total_victories, 0)
        self.assertEqual(stats.total_points_scored, 3)

    def test_recompute_accumulates_points(self) -> None:
        """Los puntos de multiples sesiones se acumulan."""
        engine = AchievementEngine()
        sessions = [
            _make_session(player_points_total=5),
            _make_session(player_points_total=8),
        ]
        stats = engine.recompute_career_stats(sessions)
        self.assertEqual(stats.total_points_scored, 13)

    def test_recompute_accumulates_rallies(self) -> None:
        """Los rallies de multiples sesiones se acumulan."""
        engine = AchievementEngine()
        sessions = [
            _make_session(max_rally=10),
            _make_session(max_rally=20),
        ]
        stats = engine.recompute_career_stats(sessions)
        self.assertEqual(stats.total_rallies, 30)


# ============================================================
# Tests de desbloqueo
# ============================================================

class UnlockTests(unittest.TestCase):
    """Tests del mecanismo de desbloqueo."""

    def test_unlock_new_returns_true(self) -> None:
        """El primer desbloqueo devuelve True."""
        engine = AchievementEngine()
        self.assertTrue(engine._unlock("career_matches_1", 0))

    def test_unlock_duplicate_returns_false(self) -> None:
        """Desbloquear dos veces devuelve False la segunda."""
        engine = AchievementEngine()
        engine._unlock("career_matches_1", 0)
        self.assertFalse(engine._unlock("career_matches_1", 0))

    def test_unlock_adds_to_notifications(self) -> None:
        """Un desbloqueo nuevo anade a pending_notifications."""
        engine = AchievementEngine()
        engine._unlock("career_matches_1", 0)
        self.assertEqual(len(engine.pending_notifications), 1)
        self.assertEqual(engine.pending_notifications[0].id, "career_matches_1")

    def test_unlock_records_date_and_session(self) -> None:
        """El registro tiene date y session_index."""
        engine = AchievementEngine()
        engine._unlock("career_matches_1", 5)
        record = engine.unlocked["career_matches_1"]
        self.assertEqual(record["session_index"], 5)
        self.assertIn("date", record)

    def test_unlock_invalid_id_returns_false(self) -> None:
        """Un ID inexistente devuelve False sin error."""
        engine = AchievementEngine()
        self.assertFalse(engine._unlock("no_existe", 0))


# ============================================================
# Tests de logros de carrera
# ============================================================

class CareerCheckTests(unittest.TestCase):
    """Tests de comprobacion de umbrales de carrera."""

    def test_first_match_unlocks_career_matches_1(self) -> None:
        """1 partido desbloquea career_matches_1."""
        engine = AchievementEngine()
        session = _make_session()
        newly = engine.check_post_match(session, 0)
        self.assertIn("career_matches_1", newly)

    def test_threshold_exact_5(self) -> None:
        """Exactamente 5 partidos desbloquea career_matches_5."""
        engine = _make_engine(total_matches=4)
        session = _make_session()
        newly = engine.check_post_match(session, 4)
        self.assertIn("career_matches_5", newly)

    def test_threshold_below_5(self) -> None:
        """4 partidos NO desbloquea career_matches_5."""
        engine = _make_engine(total_matches=3)
        session = _make_session()
        newly = engine.check_post_match(session, 3)
        self.assertNotIn("career_matches_5", newly)

    def test_multiple_thresholds_at_once(self) -> None:
        """Saltar de 0 a 10 partidos desbloquea 1, 5 y 10."""
        engine = _make_engine(total_matches=9)
        session = _make_session()
        newly = engine.check_post_match(session, 9)
        self.assertIn("career_matches_1", newly)
        self.assertIn("career_matches_5", newly)
        self.assertIn("career_matches_10", newly)

    def test_first_win_unlocks_career_wins_1(self) -> None:
        """La primera victoria desbloquea career_wins_1."""
        engine = AchievementEngine()
        session = _make_session(winner="jugador")
        newly = engine.check_post_match(session, 0)
        self.assertIn("career_wins_1", newly)

    def test_loss_does_not_unlock_wins(self) -> None:
        """Una derrota no desbloquea career_wins_1."""
        engine = AchievementEngine()
        session = _make_session(winner="ordenador")
        newly = engine.check_post_match(session, 0)
        self.assertNotIn("career_wins_1", newly)


# ============================================================
# Tests de logros de hazana
# ============================================================

class MatchFeatCheckTests(unittest.TestCase):
    """Tests de logros de un solo partido."""

    def test_rally_5_with_exact_threshold(self) -> None:
        """max_rally_hits=5 desbloquea rally_5."""
        engine = AchievementEngine()
        ctx = _make_context(max_rally_hits=5)
        newly = engine.check_realtime(ctx)
        self.assertIn("rally_5", newly)

    def test_rally_5_not_at_4(self) -> None:
        """max_rally_hits=4 NO desbloquea rally_5."""
        engine = AchievementEngine()
        ctx = _make_context(max_rally_hits=4)
        newly = engine.check_realtime(ctx)
        self.assertNotIn("rally_5", newly)

    def test_streak_3_unlocked(self) -> None:
        """Racha de 3 desbloquea streak_3."""
        engine = AchievementEngine()
        result = _make_point_result(scoring_streak=3)
        ctx = _make_context(point_result=result, winner="player")
        newly = engine.check_realtime(ctx)
        self.assertIn("streak_3", newly)

    def test_speed_180_on_fast_win(self) -> None:
        """Victoria en 170s desbloquea speed_180."""
        engine = AchievementEngine()
        session = _make_session(winner="jugador", elapsed_seconds=170)
        newly = engine.check_post_match(session, 0)
        self.assertIn("speed_180", newly)

    def test_speed_180_not_on_loss(self) -> None:
        """Derrota en 170s NO desbloquea speed_180."""
        engine = AchievementEngine()
        session = _make_session(winner="ordenador", elapsed_seconds=170)
        newly = engine.check_post_match(session, 0)
        self.assertNotIn("speed_180", newly)

    def test_perfect_match(self) -> None:
        """Victoria con 0 puntos del rival desbloquea perfect_match."""
        engine = AchievementEngine()
        session = _make_session(
            winner="jugador",
            computer_points_total=0,
            computer_games=0,
        )
        newly = engine.check_post_match(session, 0)
        self.assertIn("perfect_match", newly)
        self.assertIn("perfect_set", newly)

    def test_perfect_game_realtime(self) -> None:
        """Ganar juego con 0 pts del rival desbloquea perfect_game."""
        engine = AchievementEngine()
        result = _make_point_result(game_won=True)
        ctx = _make_context(
            point_result=result,
            winner="player",
            pre_computer_pts=0,
        )
        newly = engine.check_realtime(ctx)
        self.assertIn("perfect_game", newly)

    def test_perfect_game_not_if_opponent_scored(self) -> None:
        """Ganar juego con 1 pt del rival NO desbloquea perfect_game."""
        engine = AchievementEngine()
        result = _make_point_result(game_won=True)
        ctx = _make_context(
            point_result=result,
            winner="player",
            pre_computer_pts=1,
        )
        newly = engine.check_realtime(ctx)
        self.assertNotIn("perfect_game", newly)

    def test_comeback_set(self) -> None:
        """Ganar set tras ir perdiendo en juegos desbloquea comeback_set."""
        engine = AchievementEngine()
        engine.start_match()

        # El computer lidera en juegos
        score = _make_score(computer_games=1, player_games=0)
        ctx = _make_context(score=score)
        engine.check_realtime(ctx)

        # El player gana el set
        result = _make_point_result(set_won=True)
        score2 = _make_score(computer_games=1, player_games=2)
        ctx2 = _make_context(
            score=score2,
            point_result=result,
            winner="player",
        )
        newly = engine.check_realtime(ctx2)
        self.assertIn("comeback_set", newly)


# ============================================================
# Tests de logros secretos
# ============================================================

class SecretCheckTests(unittest.TestCase):
    """Tests de logros secretos."""

    def test_hitchhiker_42_exact(self) -> None:
        """Rally de exactamente 42 desbloquea hitchhiker_42."""
        engine = AchievementEngine()
        ctx = _make_context(rally_hits=42)
        newly = engine.check_realtime(ctx)
        self.assertIn("hitchhiker_42", newly)

    def test_hitchhiker_42_not_at_43(self) -> None:
        """Rally de 43 NO desbloquea hitchhiker_42."""
        engine = AchievementEngine()
        ctx = _make_context(rally_hits=43)
        newly = engine.check_realtime(ctx)
        self.assertNotIn("hitchhiker_42", newly)

    @patch("pong.achievements.datetime")
    def test_midnight_player_at_0200(self, mock_dt: Any) -> None:
        """Jugar a las 2:00 AM desbloquea midnight_player."""
        mock_dt.now.return_value = datetime(2026, 3, 2, 2, 0, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        engine = AchievementEngine()
        session = _make_session()
        newly = engine.check_post_match(session, 0)
        self.assertIn("midnight_player", newly)

    @patch("pong.achievements.datetime")
    def test_midnight_player_not_at_0800(self, mock_dt: Any) -> None:
        """Jugar a las 8:00 AM NO desbloquea midnight_player."""
        mock_dt.now.return_value = datetime(2026, 3, 2, 8, 0, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        engine = AchievementEngine()
        session = _make_session()
        newly = engine.check_post_match(session, 0)
        self.assertNotIn("midnight_player", newly)

    def test_all_si_with_3_answers(self) -> None:
        """3 respuestas 'Si' desbloquea all_si."""
        engine = AchievementEngine()
        history = [
            SimpleNamespace(answer="Si"),
            SimpleNamespace(answer="Si"),
            SimpleNamespace(answer="Si"),
        ]
        newly = engine.check_dialogue_achievements(history, 0)
        self.assertIn("all_si", newly)

    def test_all_si_requires_minimum_3(self) -> None:
        """2 respuestas 'Si' NO desbloquea all_si."""
        engine = AchievementEngine()
        history = [
            SimpleNamespace(answer="Si"),
            SimpleNamespace(answer="Si"),
        ]
        newly = engine.check_dialogue_achievements(history, 0)
        self.assertNotIn("all_si", newly)

    def test_all_no(self) -> None:
        """3 respuestas 'No' desbloquea all_no."""
        engine = AchievementEngine()
        history = [
            SimpleNamespace(answer="No"),
            SimpleNamespace(answer="No"),
            SimpleNamespace(answer="No"),
        ]
        newly = engine.check_dialogue_achievements(history, 0)
        self.assertIn("all_no", newly)

    def test_total_defeat(self) -> None:
        """Perder con 0 puntos desbloquea total_defeat."""
        engine = AchievementEngine()
        session = _make_session(
            winner="ordenador",
            player_points_total=0,
        )
        newly = engine.check_post_match(session, 0)
        self.assertIn("total_defeat", newly)

    def test_monochrome_win_under_30s(self) -> None:
        """Ganar en menos de 30s desbloquea monochrome_win."""
        engine = AchievementEngine()
        session = _make_session(
            winner="jugador",
            elapsed_seconds=25.0,
        )
        newly = engine.check_post_match(session, 0)
        self.assertIn("monochrome_win", newly)


# ============================================================
# Tests de logros emocionales
# ============================================================

class EmotionCheckTests(unittest.TestCase):
    """Tests de logros emocionales."""

    def test_mood_furioso_triggers(self) -> None:
        """Observar 'furioso' desbloquea mood_furioso."""
        engine = AchievementEngine()
        ctx = _make_context(mood_tag="furioso")
        newly = engine.check_realtime(ctx)
        self.assertIn("mood_furioso", newly)

    def test_mood_all_9_requires_all(self) -> None:
        """mood_all_9 requiere los 9 mood tags."""
        engine = AchievementEngine()
        engine.career_stats.moods_experienced = set(ALL_MOOD_TAGS)
        ctx = _make_context()
        newly = engine.check_realtime(ctx)
        self.assertIn("mood_all_9", newly)

    def test_mood_all_9_with_8_not_triggered(self) -> None:
        """8 moods NO desbloquea mood_all_9."""
        engine = AchievementEngine()
        engine.career_stats.moods_experienced = set(list(ALL_MOOD_TAGS)[:8])
        ctx = _make_context()
        newly = engine.check_realtime(ctx)
        self.assertNotIn("mood_all_9", newly)

    def test_win_vs_furioso(self) -> None:
        """Ganar habiendo visto furioso desbloquea win_vs_furioso."""
        engine = AchievementEngine()
        engine._match_moods_seen.add("furioso")
        session = _make_session(winner="jugador")
        newly = engine.check_post_match(session, 0)
        self.assertIn("win_vs_furioso", newly)

    def test_win_vs_furioso_not_on_loss(self) -> None:
        """Perder con furioso NO desbloquea win_vs_furioso."""
        engine = AchievementEngine()
        engine._match_moods_seen.add("furioso")
        session = _make_session(winner="ordenador")
        newly = engine.check_post_match(session, 0)
        self.assertNotIn("win_vs_furioso", newly)

    def test_record_mood_adds_unique(self) -> None:
        """record_mood solo anade moods unicos."""
        engine = AchievementEngine()
        engine.record_mood("furioso")
        engine.record_mood("furioso")
        engine.record_mood("tenso")
        self.assertEqual(len(engine._match_moods_seen), 2)
        self.assertEqual(len(engine.career_stats.moods_experienced), 2)


# ============================================================
# Tests de persistencia
# ============================================================

class PersistenceTests(unittest.TestCase):
    """Tests de save/load de logros."""

    def test_save_and_load_roundtrip(self) -> None:
        """Los logros sobreviven un ciclo save + load."""
        engine = AchievementEngine()
        engine._unlock("career_matches_1", 0)

        history: dict[str, object] = {"sessions": [], "records": {}}
        history["achievements"] = engine.get_save_data()
        history["career_stats"] = engine.get_career_stats_data()

        engine2 = AchievementEngine()
        engine2.load_from_history(history)
        self.assertTrue(engine2.is_unlocked("career_matches_1"))

    def test_load_old_format_adds_empty(self) -> None:
        """Cargar un historial sin 'achievements' no da error."""
        engine = AchievementEngine()
        old_history: dict[str, object] = {"version": "1.0", "sessions": [], "records": {}}
        engine.load_from_history(old_history)
        self.assertEqual(engine.count_unlocked(), 0)

    def test_career_stats_roundtrip(self) -> None:
        """Las career_stats sobreviven un ciclo save + load."""
        engine = AchievementEngine()
        engine.career_stats.total_matches = 10
        engine.career_stats.total_victories = 7
        engine.career_stats.moods_experienced = {"furioso", "neutral"}

        history: dict[str, object] = {"sessions": [], "records": {}}
        history["achievements"] = engine.get_save_data()
        history["career_stats"] = engine.get_career_stats_data()

        engine2 = AchievementEngine()
        engine2.load_from_history(history)
        self.assertEqual(engine2.career_stats.total_matches, 10)
        self.assertEqual(engine2.career_stats.total_victories, 7)
        self.assertIn("furioso", engine2.career_stats.moods_experienced)

    def test_retroactive_unlock_on_first_load(self) -> None:
        """Sesiones existentes desbloquean logros de carrera retroactivamente."""
        sessions = [_make_session() for _ in range(6)]
        old_history: dict[str, object] = {
            "version": "1.0",
            "sessions": sessions,
            "records": {},
        }
        engine = AchievementEngine()
        engine.load_from_history(old_history)
        # 6 sesiones -> career_matches_1 y career_matches_5 desbloqueados
        self.assertTrue(engine.is_unlocked("career_matches_1"))
        self.assertTrue(engine.is_unlocked("career_matches_5"))
        self.assertFalse(engine.is_unlocked("career_matches_10"))


# ============================================================
# Tests de notificaciones
# ============================================================

class NotificationTests(unittest.TestCase):
    """Tests de la cola de notificaciones."""

    def test_peek_empty_returns_none(self) -> None:
        """peek_notification devuelve None sin notificaciones."""
        engine = AchievementEngine()
        self.assertIsNone(engine.peek_notification())

    def test_fifo_order(self) -> None:
        """Las notificaciones se entregan en orden FIFO."""
        engine = AchievementEngine()
        engine._unlock("career_matches_1", 0)
        engine._unlock("rally_5", 0)
        notif1 = engine.peek_notification()
        assert notif1 is not None
        self.assertEqual(notif1.id, "career_matches_1")
        engine.advance_notification()
        notif2 = engine.peek_notification()
        assert notif2 is not None
        self.assertEqual(notif2.id, "rally_5")

    def test_advance_consumes(self) -> None:
        """advance_notification consume la notificacion actual."""
        engine = AchievementEngine()
        engine._unlock("career_matches_1", 0)
        self.assertTrue(engine.has_notifications())
        engine.advance_notification()
        self.assertFalse(engine.has_notifications())

    def test_notification_timer_resets(self) -> None:
        """advance_notification resetea el timer."""
        engine = AchievementEngine()
        engine._unlock("career_matches_1", 0)
        engine.set_notification_start(100.0)
        engine.advance_notification()
        self.assertIsNone(engine.get_notification_start())


# ============================================================
# Tests de check_rally y check_mood directos
# ============================================================

class CheckRallyTests(unittest.TestCase):
    """Tests de check_rally() como metodo independiente."""

    def test_rally_5_direct(self) -> None:
        """check_rally desbloquea rally_5 con max_rally_hits=5."""
        engine = AchievementEngine()
        newly = engine.check_rally(rally_hits=5, max_rally_hits=5)
        self.assertIn("rally_5", newly)

    def test_rally_5_not_at_4_direct(self) -> None:
        """check_rally NO desbloquea rally_5 con max_rally_hits=4."""
        engine = AchievementEngine()
        newly = engine.check_rally(rally_hits=4, max_rally_hits=4)
        self.assertNotIn("rally_5", newly)

    def test_rally_multiple_thresholds(self) -> None:
        """check_rally desbloquea varios umbrales de golpe si max_rally es alto."""
        engine = AchievementEngine()
        newly = engine.check_rally(rally_hits=15, max_rally_hits=15)
        self.assertIn("rally_5", newly)
        self.assertIn("rally_10", newly)
        self.assertIn("rally_15", newly)

    def test_hitchhiker_42_direct(self) -> None:
        """check_rally desbloquea hitchhiker_42 con rally_hits=42."""
        engine = AchievementEngine()
        newly = engine.check_rally(rally_hits=42, max_rally_hits=42)
        self.assertIn("hitchhiker_42", newly)

    def test_hitchhiker_42_not_at_41(self) -> None:
        """check_rally NO desbloquea hitchhiker_42 con rally_hits=41."""
        engine = AchievementEngine()
        newly = engine.check_rally(rally_hits=41, max_rally_hits=41)
        self.assertNotIn("hitchhiker_42", newly)

    def test_rally_idempotent(self) -> None:
        """check_rally no desbloquea dos veces el mismo logro."""
        engine = AchievementEngine()
        first = engine.check_rally(rally_hits=5, max_rally_hits=5)
        second = engine.check_rally(rally_hits=6, max_rally_hits=6)
        self.assertIn("rally_5", first)
        self.assertNotIn("rally_5", second)


class CheckMoodTests(unittest.TestCase):
    """Tests de check_mood() como metodo independiente."""

    def test_mood_furioso_direct(self) -> None:
        """check_mood desbloquea mood_furioso al observar 'furioso'."""
        engine = AchievementEngine()
        newly = engine.check_mood("furioso")
        self.assertIn("mood_furioso", newly)

    def test_mood_none_is_safe(self) -> None:
        """check_mood con None no falla ni desbloquea nada."""
        engine = AchievementEngine()
        newly = engine.check_mood(None)
        self.assertEqual(newly, [])

    def test_mood_all_9_direct(self) -> None:
        """check_mood desbloquea mood_all_9 cuando hay 9 moods."""
        engine = AchievementEngine()
        engine.career_stats.moods_experienced = set(ALL_MOOD_TAGS)
        newly = engine.check_mood("furioso")
        self.assertIn("mood_all_9", newly)

    def test_mood_idempotent(self) -> None:
        """check_mood no desbloquea dos veces el mismo logro."""
        engine = AchievementEngine()
        first = engine.check_mood("furioso")
        second = engine.check_mood("furioso")
        self.assertIn("mood_furioso", first)
        self.assertNotIn("mood_furioso", second)


if __name__ == "__main__":
    unittest.main()
