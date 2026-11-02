"""AI-assisted mode must not crash when CUDA is present but has no kernels.

Measured on the media matrix: every AI-assisted run failed on an RTX 50-series
GPU with a CUDA 12.6 PyTorch build ('no kernel image is available') because
torch.cuda.is_available() was trusted. Stubbed torch; no GPU needed.
"""
import unittest
from types import SimpleNamespace
from ai_sync import _device


def fake_torch(available, kernels_work):
    def arange(*a, **k):
        if k.get('device') == 'cuda' and not kernels_work:
            raise RuntimeError('CUDA error: no kernel image is available for execution on the device')
        class T:
            def reshape(self, *s): return self
            def __matmul__(self, o): return self
            def sum(self): return self
            def item(self): return 1.
        return T()
    return SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: available), arange=arange,
                           device=lambda name: SimpleNamespace(type=name))


class DeviceSelection(unittest.TestCase):
    def test_unusable_gpu_falls_back_to_cpu_with_message(self):
        said = []
        self.assertEqual(_device(fake_torch(True, False), said.append).type, 'cpu')
        self.assertIn('using CPU', said[0])

    def test_working_gpu_and_no_gpu(self):
        self.assertEqual(_device(fake_torch(True, True)).type, 'cuda')
        self.assertEqual(_device(fake_torch(False, False)).type, 'cpu')


if __name__ == '__main__':
    unittest.main()
