"""Splits a single MIDI file into left- and right-hand tracks."""

import mido
import argparse

from kalman_mapper import KalmanMapper
import kalman_mapper

class SingleFileAnnotate(object):
    def __init__(self):
        self.mapper = KalmanMapper()

    def process(self, filename):
        mapper = self.mapper
        mid = mido.MidiFile(filename)
        left_hand = mido.MidiTrack()
        right_hand = mido.MidiTrack()
        bpm = 120 #default

        new_mid = mido.MidiFile()
        left_hand_is_playing = {0}

        total_sec = 0
        total_ticks = 0
        for i, track in enumerate(mid.tracks):
            for msg in track:
                sec = mido.tick2second(msg.time, mid.ticks_per_beat, mido.bpm2tempo(bpm))
                total_sec = total_sec + sec
                total_ticks = total_ticks + msg.time
                if msg.type == "note_off" or (msg.type == "note_on" and msg.velocity==0):
                    event = kalman_mapper.MidiEvent(msg.note, is_note_on=False, when=total_sec, is_left=None)
                    mapper.midi_event(event)
                    if msg.note in left_hand_is_playing:
                        left_hand.append(msg.copy(time=total_ticks))
                        left_hand_is_playing.remove(msg.note)
                    else:
                        right_hand.append(msg.copy(time=total_ticks))
                elif msg.type == "note_on":
                    event = kalman_mapper.MidiEvent(msg.note, is_note_on=True, when=total_sec, is_left=None)
                    mapper.midi_event(event)
                    if mapper.last_was_left_hand:
                        left_hand.append(msg.copy(time=total_ticks))
                        left_hand_is_playing.add(msg.note)
                    else:
                        right_hand.append(msg.copy(time=total_ticks))
                else:
                    if msg.type == "set_tempo":
                        bpm = mido.tempo2bpm(msg.tempo)
                    left_hand.append(msg.copy(time=total_ticks))
                    right_hand.append(msg.copy(time=total_ticks))

        new_mid.tracks.append(mido.midifiles.tracks._to_reltime(right_hand))
        new_mid.tracks.append(mido.midifiles.tracks._to_reltime(left_hand))

        new_mid.save(filename.replace(".mid", "-split.mid"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, help='File path of the MIDI file to process.')
    args = parser.parse_args()
    sfa = SingleFileAnnotate()
    sfa.process(args.input)

if __name__ == '__main__':
    main()
