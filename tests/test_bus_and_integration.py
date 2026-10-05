import unittest

from oes_quantum_binaural_lab.app import LabConfig, run_lab
from oes_quantum_binaural_lab.bus import EventBus, OESControlPlane


class BusAndIntegrationTests(unittest.TestCase):
    def test_1024_classical_metric_slots_are_timestamped_and_labeled(self):
        bus = EventBus()
        plane = OESControlPlane(bus, capacity=1024)
        count = plane.fill_metric_slots([
            ("quantum_sandbox", "chsh", 2.2),
            ("stereo_binaural", "level_error", 0.01),
        ])
        events = bus.read("oes_control")
        self.assertEqual(count, 1024)
        self.assertEqual(len(plane.slots), 1024)
        self.assertEqual(len(events), 1024)
        self.assertTrue(all(e.timestamp_utc.endswith("+00:00") for e in events))
        self.assertEqual({e.payload["source_lane"] for e in events}, {"quantum_sandbox", "stereo_binaural"})
        self.assertTrue(all(isinstance(e.payload["metric_value"], float) for e in events))

    def test_bus_rejects_non_scalar_payloads_and_unknown_lanes(self):
        bus = EventBus()
        with self.assertRaises(TypeError):
            bus.publish("quantum_sandbox", "raw", {"waveform": [0.0, 1.0]})
        with self.assertRaises(ValueError):
            bus.publish("quantum_hardware", "raw", {"value": 1})

    def test_end_to_end_stays_simulated_and_uses_bus_for_metric_projection(self):
        report = run_lab(LabConfig(pair_count=8, calibration_shots_per_state=8, sweep_shots_per_pair=(1,), seed=45))
        self.assertEqual(report["oes_control"]["occupied_slots"], 1024)
        self.assertEqual(report["oes_control"]["capacity_slots"], 1024)
        self.assertFalse(report["oes_control"]["raw_quantum_states_in_oes"])
        self.assertFalse(report["oes_control"]["audio_waveforms_in_oes"])
        self.assertEqual(report["event_bus"]["lane_event_counts"]["oes_control"], 1024)
        self.assertTrue(report["event_bus"]["timestamped"])
        self.assertTrue(report["resource_use"]["simulation_only"])
        self.assertFalse(report["resource_use"]["hardware_results"])
        self.assertIn("modeling choice", report["oes_control"]["slot_semantics"])
        self.assertFalse(report["quantum_sandbox"]["readout_calibration"]["cross_pair_correlated_readout_modeled"])
        self.assertTrue(report["stereo_binaural"]["scope"].startswith("digital stereo"))

    def test_bus_rejects_oversized_or_serialized_array_strings(self):
        bus = EventBus()
        with self.assertRaises(ValueError):
            bus.publish("quantum_sandbox", "reported_metric", {"metric_name": "[0.1, 0.2, 0.3]"})
        with self.assertRaises(ValueError):
            bus.publish("quantum_sandbox", "reported_metric", {"metric_name": "x" * 65})
        with self.assertRaises(ValueError):
            bus.publish("quantum_sandbox", "reported_metric", {"metric_name": "wave;drop"})
        # Short labels remain accepted.
        event = bus.publish("quantum_sandbox", "reported_metric", {"metric_name": "chsh_raw", "metric_value": 1.0})
        self.assertEqual(event.payload["metric_name"], "chsh_raw")



if __name__ == "__main__":
    unittest.main()
