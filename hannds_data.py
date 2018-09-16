import glob
import logging
import math
import os
import random
from collections import namedtuple

import numpy as np
import pretty_midi
from torch.utils.data import Dataset, DataLoader
from torch.utils.data.sampler import Sampler

logging.basicConfig(level=logging.DEBUG)


class AllData(object):
    def __init__(self, debug=False):
        self._convert('data/', overwrite=False)
        self.train_files = self.valid_files = self.test_files = None
        self.debug = debug

    def initialize_from_dir(self, len_train_sequence):
        all_files = self._get_files_from_path('data/', ['*.npy'])
        r = random.Random(42)  # seed is arbitrary
        r.shuffle(all_files)
        n_valid_test = math.ceil(len(all_files) * 0.15)
        n_train = len(all_files) - n_valid_test * 2
        range_train = (0, n_train)
        range_valid = (range_train[1], range_train[1] + n_valid_test)
        range_test = (range_valid[1], range_valid[1] + n_valid_test)
        assert range_test[1] == len(all_files)

        self.train_files = all_files[range_train[0]: range_train[1]]
        self.valid_files = all_files[range_valid[0]: range_valid[1]]
        self.test_files = all_files[range_test[0]: range_test[1]]
        self._make_datasets(len_train_sequence)

    def initialize_from_lists(self, train_files, valid_files, test_files, len_train_sequence):
        self.train_files = train_files.copy()
        self.valid_files = valid_files.copy()
        self.test_files = test_files.copy()
        self._make_datasets(len_train_sequence)

    def _make_datasets(self, len_train_sequence):
        self.train_data = self._dataset_for_files(self.train_files, len_train_sequence, debug=self.debug)
        self.valid_data = self._dataset_for_files(self.valid_files, len_sequence=-1, debug=self.debug)
        self.test_data = self._dataset_for_files(self.test_files, len_sequence=-1, debug=self.debug)

    def _get_files_from_path(self, path, extensions):
        if os.path.isfile(path):  # Load single file
            files = [path]
        else:  # Get list of all files with correct extensions in path
            files = []
            for file_type in extensions:
                files.extend(glob.glob(os.path.join(path, file_type)))

            if len(files) == 0:
                raise FileNotFoundError('No files found with correct extensions ' + str(extensions))
        return sorted(files)

    def _convert(self, path, ms_window=20, overwrite=True):
        midi_files = self._get_files_from_path(path, ['*.mid', '*.midi'])

        samples_per_sec = 1000 // ms_window
        for midi_file in midi_files:
            npy_file = midi_file + '_' + str(ms_window) + 'ms' + '.npy'

            if overwrite or not os.path.exists(npy_file):
                midi = pretty_midi.PrettyMIDI(midi_file)
                logging.debug("Converting file '" + midi_file + "'")
                midi_data = midi.instruments[0], midi.instruments[1]

                # Generate empty numpy arrays
                n_windows = math.ceil(midi.get_end_time() * samples_per_sec)
                hands = np.zeros((
                    n_windows,  # Number of windows to calculate
                    2,  # Left and right hand = 2 hands
                    88  # 88 keys on a piano
                ), dtype=np.bool)

                # Fill array with data
                for hand, midi_hand in enumerate(midi_data):
                    for note in midi_hand.notes:
                        start = int(math.floor(note.start * samples_per_sec))
                        end = int(math.ceil(note.end * samples_per_sec))
                        hands[start:end, hand, note.pitch - 21] = True

                # Save array to disk
                np.save(npy_file, hands)

    def _dataset_for_files(self, npy_files, len_sequence, debug=False):
        if debug:
            npy_data = np.concatenate([np.load(npy_file) for npy_file in npy_files[:2]], axis=0)
        else:
            npy_data = np.concatenate([np.load(npy_file) for npy_file in npy_files], axis=0)

        data_set = HanndsDataset(npy_data, len_sequence)
        return data_set


XY = namedtuple('XY', ['X', 'Y'])

LEFT_HAND_LABEL = 1
RIGHT_HAND_LABEL = 2


class HanndsDataset(Dataset):
    """
    provides the Hannds dataset as (overlapping) sequences of size
    len_sequence. If len_sequenc == -1, it provides a single sequence
    of maximal length.
    """

    def __init__(self, npy_data, len_sequence):
        self.len_sequence = len_sequence
        self.data = XY(*self._compute_X_Y(npy_data))

    def _compute_X_Y(self, data):
        data = data.astype(np.bool)

        batch_size = data.shape[0]
        # Merge both hands in a single array
        X = np.logical_or(
            data[:, 0, :],
            data[:, 1, :]
        )

        Y = np.zeros((batch_size, 88))
        Y[data[:, 0, :]] = LEFT_HAND_LABEL
        Y[data[:, 1, :]] = RIGHT_HAND_LABEL
        return X.astype(np.float32), Y.astype(np.longlong)

    def __len__(self):
        if self.len_sequence == -1:
            return 1
        else:
            return self.data.X.shape[0] // self.len_sequence - 1

    def __getitem__(self, idx):
        if self.len_sequence == -1:
            return self.data.X, self.data.Y
        else:
            start = idx * self.len_sequence
            end = start + self.len_sequence
            res1 = self.data.X[start: end]
            res2 = self.data.Y[start: end]
            assert res1.shape[0] == res2.shape[0] == self.len_sequence
            return res1, res2


class ContinuationSampler(Sampler):

    def __init__(self, len_dataset, batch_size):
        Sampler.__init__(self, None)
        self.len_dataset = len_dataset
        self.batch_size = batch_size

    def __iter__(self):
        return iter(self._generate_indices())

    def __len__(self):
        num_batches = self.len_dataset // self.batch_size
        return num_batches * self.batch_size

    def _generate_indices(self):
        num_batches = step = self.len_dataset // self.batch_size
        for i in range(num_batches):
            index = i
            for j in range(self.batch_size):
                yield index
                index += step

        raise StopIteration


def main():
    data = AllData(len_train_sequence=100, debug=True)
    data._convert('data/', overwrite=False)

    import matplotlib.pyplot as plt

    train_data = data.train_data
    batchX, batchY = train_data[0]
    print(batchX.shape)
    print(batchY.shape)

    batch_size = 20
    continuity = ContinuationSampler(len(train_data), batch_size)
    loader = DataLoader(train_data, batch_size, sampler=continuity)

    for idx, (X_batch, Y_batch) in enumerate(loader):
        X = X_batch[8]
        Y = Y_batch[8]
        img = np.full((X.shape[0] + 2, X.shape[1]), -0.2)
        img[:-2] = X
        img[-1] = Y[-1, :] - 1.0

        plt.imshow(img, cmap='bwr', origin='lower', vmin=-1, vmax=1)
        plt.show()


if __name__ == '__main__':
    main()
