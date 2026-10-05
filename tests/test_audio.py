import unittest

from oes_quantum_binaural_lab.audio import AudioSettings, max_unambiguous_delay_samples, run_stereo_calibration


class StereoCalibrationTests(unittest.TestCase):
    def test_digital_loopback_recovers_known_synthetic_settings(self):
        result = run_stereo_calibration(seed=22)
        recovery = result["recovery"]
        self.assertLess(abs(recovery["left_level_error"]), 0.003)
        self.assertLess(abs(recovery["right_level_error"]), 0.003)
        self.assertLess(abs(recovery["left_phase_error_deg"]), 0.1)
        self.assertLess(abs(recovery["right_phase_error_deg"]), 0.1)
        self.assertLess(abs(recovery["delay_error_samples"]), 0.05)
        self.assertLess(recovery["crosstalk_abs_error"], 0.003)
        self.assertEqual(recovery["clipped_sample_count_across_channels"], 0)
        self.assertIn("no audio interface", result["scope"])
        self.assertEqual(result["playback"], "disabled; samples remain in memory")

    def test_clipping_is_detected_and_configurable(self):
        settings = AudioSettings(left_level=3.0, right_level=2.5, clip_threshold=0.7, noise_std=0.0)
        result = run_stereo_calibration(settings, seed=1)
        self.assertGreater(result["recovery"]["clipped_sample_count_across_channels"], 0)
        self.assertGreater(result["recovery"]["clipped_fraction"], 0.0)
        self.assertLessEqual(result["recovery"]["peak_before_clipping"], 3.0)

    def test_rejects_frame_delay_combo_that_aliases_phase_unwrapping(self):
        self.assertEqual(max_unambiguous_delay_samples(1024), 32)
        with self.assertRaises(ValueError) as ctx:
            run_stereo_calibration(AudioSettings(frames=1024, right_delay_samples=64), seed=3)
        self.assertIn("aliases phase unwrapping", str(ctx.exception))
        # Default frames=4096 with delay=3 remains valid and recovers.
        ok = run_stereo_calibration(AudioSettings(frames=4096, right_delay_samples=3), seed=3)
        self.assertLess(abs(ok["recovery"]["delay_error_samples"]), 0.05)

    def test_zero_channel_level_reports_crosstalk_unavailable(self):
        left_zero = run_stereo_calibration(
            AudioSettings(left_level=0.0, right_level=0.5, crosstalk=0.04, noise_std=0.0),
            seed=5,
        )["recovery"]
        self.assertIsNone(left_zero["estimated_crosstalk_right_from_left"])
        self.assertIsNotNone(left_zero["estimated_crosstalk_left_from_right"])
        self.assertIsNone(left_zero["estimated_crosstalk"])
        self.assertIsNone(left_zero["crosstalk_abs_error"])

        right_zero = run_stereo_calibration(
            AudioSettings(left_level=0.5, right_level=0.0, crosstalk=0.04, noise_std=0.0),
            seed=5,
        )["recovery"]
        self.assertIsNone(right_zero["estimated_crosstalk_left_from_right"])
        self.assertIsNotNone(right_zero["estimated_crosstalk_right_from_left"])
        self.assertIsNone(right_zero["estimated_crosstalk"])
        self.assertIsNone(right_zero["crosstalk_abs_error"])



if __name__ == "__main__":
    unittest.main()
