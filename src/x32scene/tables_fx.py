"""FX decoding tables: effect short-codes and the graphic-EQ band labels. Parameter
orders live in ``services.fx.FX_PARAMS``. Source: Maillot, Unofficial X32/M32 OSC Remote
Protocol v4.06, checked against a console.
"""

from __future__ import annotations

FX_CODES = {
    'HALL': 'Hall Reverb',
    'TEQ': 'Stereo TrueEQ',
    'AMBI': 'Ambiance',
    'DES2': 'Dual DeEsser',
    'RPLT': 'Rich Plate Reverb',
    'DES': 'Stereo DeEsser',
    'ROOM': 'Room Reverb',
    'P1A': 'Stereo Xtec EQ1',
    'CHAM': 'Chamber Reverb',
    'P1A2': 'Dual Xtec EQ1',
    'PLAT': 'Plate Reverb',
    'PQ5': 'Stereo Xtec EQ5',
    'VREV': 'Vintage Reverb',
    'PQ5S': 'Dual Xtec EQ5',
    'VRM': 'Vintage Room',
    'WAVD': 'Wave Designer',
    'GATE': 'Gated Reverb',
    'LIM': 'Limiter',
    'RVRS': 'Reverse Reverb',
    'CMB': 'Combinator',
    'DLY': 'Stereo Delay',
    'CMB2': 'Dual Combinator',
    '3TAP': '3-Tap Delay',
    'FAC': 'Fair Comp',
    '4TAP': 'Rhythm Delay',
    'FAC1M': 'M/S Fair Comp',
    'CRS': 'Stereo Chorus',
    'FAC2': 'Dual Fair Comp',
    'FLNG': 'Stereo Flanger',
    'LEC': 'Leisure Comp',
    'PHAS': 'Stereo Phaser',
    'LEC2': 'Dual Leisure Comp',
    'DIMC': 'Dimension-C',
    'ULC': 'Ultimo Comp',
    'FILT': 'Mood Filter',
    'ULC2': 'Dual Ultimo Comp',
    'ROTA': 'Rotary Speaker',
    'ENH2': 'Dual Enhancer',
    'PAN': 'Tremolo/Panner',
    'ENH': 'Stereo Enhancer',
    'SUB': 'Suboctaver',
    'EXC2': 'Dual Exciter',
    'D/RV': 'Delay+Chamber',
    'EXC': 'Exciter',
    'CR/R': 'Chorus + Chamber',
    'IMG': 'Stereo Imager',
    'FL/R': 'Flanger+Chamber',
    'EDI': 'Edison EX1',
    'D/CR': 'Delay + Chorus',
    'SON': 'Sound Maxer',
    'D/FL': 'Delay+Flanger',
    'AMP2': 'Dual Guitar Amp',
    'MODD': 'Modulation Delay',
    'AMP': 'Stereo Guitar Amp',
    'GEQ2': 'Graphic EQ (dual)',
    'DRV2': 'Dual Tube Stage',
    'GEQ': 'Graphic EQ',
    'DRV': 'Stereo Tube Stage',
    'TEQ2': 'Dual TrueEQ',
    'PIT2': 'Dual Pitch Shifter',
    'PIT': 'Stereo Pitch',
}


def decode_fx(code: str) -> str:
    return FX_CODES.get(code, code)




# ISO 1/3-octave center frequencies, 20 Hz-20 kHz, 31 bands — GEQ/GEQ2's band count and
# range endpoints are console-manual-confirmed; individual band labels are the standard
# ISO series, not console-verified one-by-one.
GEQ_BAND_LABELS = (
    "20", "25", "31.5", "40", "50", "63", "80", "100", "125", "160",
    "200", "250", "315", "400", "500", "630", "800", "1000", "1250", "1600",
    "2000", "2500", "3150", "4000", "5000", "6300", "8000", "10000", "12500", "16000",
    "20000",
)


def geq_param_names(dual: bool) -> list[str]:
    """Param names for a GEQ (dual=False, 32 slots: 31 bands + Master) or GEQ2
    (dual=True, 64 slots: 31 bands + Master, per side A/B)."""
    if not dual:
        return [*GEQ_BAND_LABELS, "Master"]
    return (
        [f"{b} A" for b in GEQ_BAND_LABELS] + ["Master A"]
        + [f"{b} B" for b in GEQ_BAND_LABELS] + ["Master B"]
    )


# parameter names in /fx/N/par order, per effect short-code
FX_PARAMS = {
    "PLAT": ["PreDelay", "Decay", "Size", "Damp", "Diff", "Level",
             "LoCut", "HiCut", "BassMult", "Xover", "ModDepth", "ModSpeed"],
    "VRM": ["RevDelay", "Decay", "RoomSize", "Density", "ERLevel", "Level",
            "Low", "High", "LoCut", "HiCut", "ERDelayL", "ERDelayR", "Freeze"],
    "D/CR": ["Time", "Pattern", "FeedHC", "Feed", "Xfeed", "Bal",
             "Speed", "Depth", "Delay", "Phase", "Wave", "Mix"],
    "CR/R": ["Speed", "Depth", "Delay", "Phase", "Wave", "Balance",
             "PreDelay", "Decay", "Size", "Damping", "LoCut", "Mix"],
    "EXC": ["Tune", "Peak", "Zero Fill", "Timbre", "Harmonics", "Mix", "Solo"],
    "LIM": ["Input Gain", "Out Gain", "Squeeze", "Knee", "Attack", "Release",
            "Stereo Link", "Auto Gain"],
    "HALL": ["Pre Delay", "Decay", "Size", "Damping", "Diffuse", "Level", "Lo Cut",
             "Hi Cut", "Bass Multi", "Spread", "Shape", "Mod Speed"],
    "DLY": ["Mix", "Time", "Mode", "Factor L", "Factor R", "Offset L/R", "Lo Cut", "Hi Cut",
            "Feed Lo Cut", "Feed Left", "Feed Right", "Feed Hi Cut"],
    "CRS": ["Speed", "Depth L", "Depth R", "Delay L", "Delay R", "Mix", "Lo Cut", "Hi Cut",
            "Phase", "Wave", "Spread"],
    "SUB": ["Active A", "Range A", "Dry A", "Octave -1 A", "Octave -2 A",
            "Active B", "Range B", "Dry B", "Octave -1 B", "Octave -2 B"],
    "3TAP": ["Time", "Gain Base", "Pan Base", "Feedback", "Lo Cut", "Hi Cut", "Factor A", "Gain A", "Pan A", "Factor B", "Gain B", "Pan B", "Cross Feed", "Mono", "Dry"],
    "AMBI": ["Pre Delay", "Decay", "Size", "Damping", "Diffuse", "Level", "Lo Cut", "Hi Cut", "Modulate", "Tail Gain"],
    "AMP": ["Preamp", "Buzz", "Punch", "Crunch", "Drive", "Level", "Low", "High", "Cabinet"],
    "D/FL": ["Time", "Pattern", "Feed Hi Cut", "Feedback", "Cross Feed", "Balance", "Speed", "Depth", "Delay", "Phase", "Feed", "Mix"],
    "D/RV": ["Time", "Pattern", "Feed Hi Cut", "Feedback", "Cross Feed", "Balance", "Pre Delay", "Decay", "Size", "Damping", "Lo Cut", "Mix"],
    "DRV": ["Drive", "Even Har", "Odd Har", "Gain", "Lo Cut", "Hi Cut", "Lo Gain", "Lo Freq", "Hi Gain", "Hi Freq"],
    "ENH": ["Out Gain", "Spread", "Bass Gain", "Bass Freq", "Mid Gain", "Mid Q", "Hi Gain", "Hi Freq", "Solo"],
    "ENH2": ["Out Gain A", "Bass Gain A", "Bass Freq A", "Mid Gain A", "Mid Q A", "Hi Gain A", "Hi Freq A", "Solo A", "Out Gain B", "Bass Gain B", "Bass Freq B", "Mid Gain B", "Mid Q B", "Hi Gain B", "Hi Freq B", "Solo B"],
    "EXC2": ["Tune A", "Peak A", "Zero Fill A", "Timbre A", "Harmonics A", "Mix A", "Solo A", "Tune B", "Peak B", "Zero Fill B", "Timbre B", "Harmonics B", "Mix B", "Solo B"],
    "FILT": ["Speed", "Depth", "Resonance", "Base", "Mode", "Mix", "Wave", "Phase", "Env. Modulation", "Attack", "Release", "Drive", "4 Pole", "Side Chain"],
    "FL/R": ["Speed", "Depth", "Delay", "Phase", "Feed", "Balance", "Pre Delay", "Decay", "Size", "Damping", "Lo Cut", "Mix"],
    "FLNG": ["Speed", "Depth L", "Depth R", "Delay L", "Delay R", "Mix", "Lo Cut", "Hi Cut", "Phase", "Feed Lo Cut", "Feed Hi Cut", "Feed"],
    "GATE": ["Pre Delay", "Decay", "Attack", "Density", "Spread", "Level", "Lo Cut", "Hi Shv Freq", "Hi Shv Gain", "Diffuse"],
    "IMG": ["Balance", "Mono Pan", "Stereo Pan", "Shv Gain", "Shv Freq", "Shv Q", "Out Gain"],
    "PAN": ["Speed", "Phase", "Wave", "Depth", "Env. Speed", "Env. Depth", "Attack", "Hold", "Release"],
    "PHAS": ["Speed", "Depth", "Resonance", "Base", "Stages", "Mix", "Wave", "Phase", "Env. Modulation", "Attack", "Hold", "Release"],
    "PIT2": ["Semitone 1", "Cent 1", "Delay 1", "Gain 1", "Pan 1", "Mix", "Semitone 2", "Cent 2", "Delay 2", "Gain 2", "Pan 2", "Hi Cut"],
    "ROTA": ["Lo Speed", "Hi Speed", "Accelerate", "Distance", "Balance", "Mix", "Stop", "Slow"],
    "RVRS": ["Pre Delay", "Decay", "Rise", "Diffuse", "Spread", "Level", "Lo Cut", "Hi Shv Freq", "Hi Shv Gain"],
    "VREV": ["Pre Delay", "Decay", "Modulate", "Vintage", "Position", "Level", "Lo Cut", "Hi Cut", "Lo Multiply", "Hi Multiply"],
    "WAVD": ["Attack A", "Sustain A", "Gain A", "Attack B", "Sustain B", "Gain B"],
    "4TAP": ["Time", "Gain Base", "Feedback", "Lo Cut", "Hi Cut", "Spread", "Factor A", "Gain A", "Factor B", "Gain B", "Factor C", "Gain C", "Cross Feed", "Mono", "Dry"],
    "AMP2": ["Preamp A", "Buzz A", "Punch A", "Crunch A", "Drive A", "Level A", "Low A", "High A", "Cabinet A", "Preamp B", "Buzz B", "Punch B", "Crunch B", "Drive B", "Level B", "Low B", "High B", "Cabinet B"],
    "CHAM": ["Pre Delay", "Decay", "Size", "Damping", "Diffuse", "Level", "Lo Cut", "Hi Cut", "Bass Multi", "Spread", "Shape", "Spin", "Reflection L", "Reflection R", "Reflection Gain L", "Reflection Gain R"],
    "CMB": ["Active", "Band Solo", "Mix", "Attack", "Release", "Autorelease", "SBC Speed", "SBC On", "Xover", "Xover Slope", "Ratio", "Threshold", "Gain", "Band 1 Threshold", "Band 1 Gain", "Band 1 Lock", "Band 2 Threshold", "Band 2 Gain", "Band 2 Lock", "Band 3 Threshold", "Band 3 Gain", "Band 3 Lock", "Band 4 Threshold", "Band 4 Gain", "Band 4 Lock", "Band 5 Threshold", "Band 5 Gain", "Band 5 Lock", "Meter Mode"],
    "CMB2": ["Active A", "Band Solo A", "Mix A", "Attack A", "Release A", "Autorelease A", "SBC Speed A", "SBC On A", "Xover A", "Xover Slope A", "Ratio A", "Threshold A", "Gain A", "Band 1 Threshold A", "Band 1 Gain A", "Band 1 Lock A", "Band 2 Threshold A", "Band 2 Gain A", "Band 2 Lock A", "Band 3 Threshold A", "Band 3 Gain A", "Band 3 Lock A", "Band 4 Threshold A", "Band 4 Gain A", "Band 4 Lock A", "Band 5 Threshold A", "Band 5 Gain A", "Band 5 Lock A", "Meter Mode A", "Active B", "Band Solo B", "Mix B", "Attack B", "Release B", "Autorelease B", "SBC Speed B", "SBC On B", "Xover B", "Xover Slope B", "Ratio B", "Threshold B", "Gain B", "Band 1 Threshold B", "Band 1 Gain B", "Band 1 Lock B", "Band 2 Threshold B", "Band 2 Gain B", "Band 2 Lock B", "Band 3 Threshold B", "Band 3 Gain B", "Band 3 Lock B", "Band 4 Threshold B", "Band 4 Gain B", "Band 4 Lock B", "Band 5 Threshold B", "Band 5 Gain B", "Band 5 Lock B", "Meter Mode B"],
    "DES": ["Lo Band L", "Hi Band L", "Lo Band R", "Hi Band R", "Voice", "Mode"],
    "DES2": ["Lo Band A", "Hi Band A", "Lo Band B", "Hi Band B", "Voice A", "Voice B"],
    "DIMC": ["Active", "Mode", "Dry", "Mode 1", "Mode 2", "Mode 3", "Mode 4"],
    "DRV2": ["Drive A", "Even Har A", "Odd Har A", "Gain A", "Lo Cut A", "Hi Cut A", "Lo Gain A", "Lo Freq A", "Hi Gain A", "Hi Freq A", "Drive B", "Even Har B", "Odd Har B", "Gain B", "Lo Cut B", "Hi Cut B", "Lo Gain B", "Lo Freq B", "Hi Gain B", "Hi Freq B"],
    "EDI": ["Active", "Stereo Input", "Stereo Output", "ST Spread", "LMF Spread", "Balance", "Center Distance", "Out Gain"],
    "FAC": ["Active", "Input Gain", "Threshold", "Time", "Bias", "Gain", "Balance"],
    "FAC1M": ["Active", "Input Gain M", "Threshold M", "Time M", "Bias M", "Gain M", "Balance M", "Input Gain S", "Threshold S", "Time S", "Bias S", "Gain S", "Balance S"],
    "FAC2": ["Active A", "Input Gain A", "Threshold A", "Time A", "Bias A", "Gain A", "Balance A", "Active B", "Input Gain B", "Threshold B", "Time B", "Bias B", "Gain B", "Balance B"],
    "LEC": ["Active", "Gain", "Peak", "Mode", "Out Gain"],
    "LEC2": ["Active A", "Gain A", "Peak A", "Mode A", "Out Gain A", "Active B", "Gain B", "Peak B", "Mode B", "Out Gain B"],
    "MODD": ["Time", "Delay", "Feed", "Lo Cut", "Hi Cut", "Depth", "Rate", "Setup", "Type", "Decay", "Damping", "Balance", "Mix"],
    "P1A": ["Active", "Gain", "Lo Boost", "Lo Freq", "Lo Att", "Hi Width", "Hi Boost", "Hi Freq", "Att Sel", "Att Freq", "Transformer"],
    "P1A2": ["Active A", "Gain A", "Lo Boost A", "Lo Freq A", "Lo Att A", "Hi Width A", "Hi Boost A", "Hi Freq A", "Att Sel A", "Att Freq A", "Transformer A", "Active B", "Gain B", "Lo Boost B", "Lo Freq B", "Lo Att B", "Hi Width B", "Hi Boost B", "Hi Freq B", "Att Sel B", "Att Freq B", "Transformer B"],
    "PIT": ["Semitone", "Cent", "Delay", "Lo Cut", "Hi Cut", "Mix"],
    "PQ5": ["Active", "Gain", "Lo Freq", "Lo Boost", "Mid Freq", "Mid Boost", "Hi Freq", "Hi Boost", "Transformer"],
    "PQ5S": ["Active A", "Gain A", "Lo Freq A", "Lo Boost A", "Mid Freq A", "Mid Boost A", "Hi Freq A", "Hi Boost A", "Transformer A", "Active B", "Gain B", "Lo Freq B", "Lo Boost B", "Mid Freq B", "Mid Boost B", "Hi Freq B", "Hi Boost B", "Transformer B"],
    "ROOM": ["Pre Delay", "Decay", "Size", "Damping", "Diffuse", "Level", "Lo Cut", "Hi Cut", "Bass Multi", "Spread", "Shape", "Spin", "Echo L", "Echo R", "Echo Feed L", "Echo Feed R"],
    "RPLT": ["Pre Delay", "Decay", "Size", "Damping", "Diffuse", "Level", "Lo Cut", "Hi Cut", "Bass Multi", "Spread", "Attack", "Spin", "Echo L", "Echo R", "Echo Feed L", "Echo Feed R"],
    "SON": ["Active A", "Lo Contour A", "Process A", "Out Gain A", "Active B", "Lo Contour B", "Process B", "Out Gain B"],
    "ULC": ["Active", "Input Gain", "Out Gain", "Attack", "Release", "Ratio"],
    "ULC2": ["Active A", "Input Gain A", "Out Gain A", "Attack A", "Release A", "Ratio A", "Active B", "Input Gain B", "Out Gain B", "Attack B", "Release B", "Ratio B"],
}

# /fx/[1-4]/type and /fx/[5-8]/type enumeration order (an int over OSC), and the
# display-type int an effect preset header carries (protocol appendix)
FX_TYPES = ("HALL", "AMBI", "RPLT", "ROOM", "CHAM", "PLAT", "VREV", "VRM", "GATE", "RVRS",
    "DLY", "3TAP", "4TAP", "CRS", "FLNG", "PHAS", "DIMC", "FILT", "ROTA", "PAN", "SUB", "D/RV",
    "CR/R", "FL/R", "D/CR", "D/FL", "MODD", "GEQ2", "GEQ", "TEQ2", "TEQ", "DES2", "DES", "P1A",
    "P1A2", "PQ5", "PQ5S", "WAVD", "LIM", "CMB", "CMB2", "FAC", "FAC1M", "FAC2", "LEC", "LEC2",
    "ULC", "ULC2", "ENH2", "ENH", "EXC2", "EXC", "IMG", "EDI", "SON", "AMP2", "AMP", "DRV2",
    "DRV", "PIT2", "PIT")
FX_SIDE_RACK_TYPES = frozenset({"GEQ2", "GEQ", "TEQ2", "TEQ", "DES2", "DES", "P1A", "P1A2",
    "PQ5", "PQ5S", "WAVD", "LIM", "FAC", "FAC1M", "FAC2", "LEC", "LEC2", "ULC", "ULC2", "ENH2",
    "ENH", "EXC2", "EXC", "IMG", "EDI", "SON", "AMP2", "AMP", "DRV2", "DRV", "PHAS", "FILT",
    "PAN", "SUB"})
FX_DISPLAY_TYPE = {"HALL": 0, "AMBI": 5, "RPLT": 3, "ROOM": 2, "CHAM": 1, "PLAT": 4, "VREV": 9,
    "VRM": 8, "GATE": 6, "RVRS": 7, "DLY": 20, "3TAP": 21, "4TAP": 22, "CRS": 10, "FLNG": 11,
    "PHAS": 27, "DIMC": 58, "FILT": 41, "ROTA": 28, "PAN": 40, "SUB": 57, "D/RV": 16, "CR/R":
    14, "FL/R": 15, "D/CR": 17, "D/FL": 18, "MODD": 19, "GEQ2": 24, "GEQ": 23, "TEQ2": 26,
    "TEQ": 25, "DES2": 43, "DES": 42, "P1A": 44, "P1A2": 45, "PQ5": 46, "PQ5S": 47, "WAVD": 29,
    "LIM": 30, "CMB": 59, "CMB2": 60, "FAC": 48, "FAC1M": 49, "FAC2": 50, "LEC": 51, "LEC2": 52,
    "ULC": 53, "ULC2": 54, "ENH2": 32, "ENH": 31, "EXC2": 34, "EXC": 33, "IMG": 39, "EDI": 56,
    "SON": 55, "AMP2": 36, "AMP": 35, "DRV2": 38, "DRV": 37, "PIT2": 13, "PIT": 12}

# the parameter tokens a console writes when a slot switches to the type: what an edit
# that changes a type must write, and each slot's token format; the 64-token line's
# trailing zeros omitted
FX_DEFAULTS = {
    "HALL": "20 1.57 60 5k74 25 0.0 83 7k2 0.95 25 50 30",
    "AMBI": "4 0.84 60 5k06 30 0.0 71 7k9 20 50",
    "RPLT": "10 1.70 27 4k47 100 0.0 89 5k0 0.81 18 26 50 90 80 34 -28",
    "ROOM": "6 0.43 18 3k94 68 1.5 83 5k0 1.00 18 40 25 10 20 0 0",
    "CHAM": "14 1.70 56 4k47 100 0.0 60 5k0 1.00 33 70 50 115 135 54 66",
    "PLAT": "32 2.11 60 6k50 30 0.0 60 7k2 1.09 211.44 20 20",
    "VREV": "40 3.0 100 OFF FRONT 0.0 76 11k9 1.00 0.70",
    "VRM": "20 2.16 24 30 22 0.0 1.10 0.69 89 10k4 28 34 OFF",
    "GATE": "8 312 6 22 60 0.0 65 5k0 -12.0 30",
    "RVRS": "30 624 28 24 78 0.0 105 7k9 -12.0",
    "DLY": "100 223 X 1 1 13 10 20k0 97 30 30 20k0",
    "3TAP": "200 100 0 30.0 10 20k0 4/3 50 -100 3/2 60 100 OFF OFF OFF",
    "4TAP": "200 100 30.0 10 20k0 5 4/3 50 1 50 3/2 50 OFF OFF OFF",
    "CRS": "0.48 20 20 15.1 16.6 100 83 10k4 120 100 100",
    "FLNG": "0.32 80 80 4.2 4.2 100 83 15k1 180 122 11k5 70",
    "PHAS": "1.44 54 42 28 4 70 -25 0 0 21 52 209",
    "DIMC": "ON ST OFF ON OFF ON OFF",
    "FILT": "0.20 0 70 104.7 LP 100 TRI 90 64 12 143 60 4POL OFF",
    "ROTA": "0.66 5.01 38 0 -15 100 RUN SLOW",
    "PAN": "1.44 180 0 100 0 0 21 52 209",
    "SUB": "ON LO 100 30 0 ON LO 100 30 0",
    "D/RV": "240 3/4 7k6 40.0 40 +0 24 1.43 52 5k6 89 100",
    "CR/R": "0.47 20 15.1 180 100 +10 20 1.32 40 6k4 83 100",
    "FL/R": "0.41 80 2.2 25 70 -15 14 0.97 24.0 7k2 113 100",
    "D/CR": "201 1 9k7 30.0 40 +60 1.07 20 15.1 100 100 100",
    "D/FL": "185 1 9k7 38.0 30 +50 0.56 80 4.2 180 80 100",
    "MODD": "300 1 30.0 97 9k5 20 1.08 SER CLUB 5.0 5k6 +0 100",
    "GEQ2": "0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 "
            "0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 "
            "0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 "
            "0.0 0.0 0.0 0.0",
    "GEQ": "0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 "
            "0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0",
    "TEQ2": "0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 "
            "0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 "
            "0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 "
            "0.0 0.0 0.0 0.0",
    "TEQ": "0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 "
            "0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0",
    "DES2": "0.0 0.0 0.0 0.0 FEM FEM",
    "DES": "0.0 0.0 0.0 0.0 FEM ST",
    "P1A": "ON 0.0 0.0 20 0.0 0.6 0.0 12k 0.0 20k ON",
    "P1A2": "ON 0.0 0.0 20 0.0 0.6 0.0 12k 0.0 20k ON ON 0.0 0.0 20 0.0 0.6 0.0 12k 0.0 20k ON",
    "PQ5": "ON 0.0 200 0.0 1k5 0.0 4k 0.0 ON",
    "PQ5S": "OFF 0.0 200 0.0 200 0.0 1k5 0.0 OFF OFF 0.0 200 0.0 200 0.0 1k5 0.0 OFF",
    "WAVD": "0 0 0.0 0 0 0.0",
    "LIM": "0.0 -0.5 0 3 0.05 662 ON OFF",
    "CMB": "ON OFF 100 5 494 ON 5 ON 0 48 3 0.0 0.0 0.0 0.0 0 0.0 0.0 0 0.0 0.0 0 0.0 0.0 0 "
            "0.0 0.0 0 GR",
    "CMB2": "ON OFF 100 5 494 ON 5 ON 0 48 3 0.0 0.0 0.0 0.0 0 0.0 0.0 0 0.0 0.0 0 0.0 0.0 0 "
            "0.0 0.0 0 GR ON OFF 100 5 494 ON 5 ON 0 48 3 0.0 0.0 0.0 0.0 0 0.0 0.0 0 0.0 0.0 "
            "0 0.0 0.0 0 0.0 0.0 0 GR",
    "FAC": "ON -8.0 5.0 2 50 -8.5 55",
    "FAC1M": "ON -8.0 5.0 2 50 -8.5 55 -8.0 5.0 2 50 -8.5 55",
    "FAC2": "ON -8.0 5.0 2 50 -8.5 55 ON -8.0 5.0 2 50 -8.5 55",
    "LEC": "ON 44 48 COMP 1.0",
    "LEC2": "ON 44 48 COMP 1.0 ON 44 48 COMP 1.0",
    "ULC": "ON -24 -23 3.7 1.9 4",
    "ULC2": "ON -24 -23 3.7 1.9 4 ON -24 -23 3.7 1.9 4",
    "ENH2": "0.0 14 20 12 38 16 50 OFF 0.0 14 20 12 38 16 50 OFF",
    "ENH": "0.0 22 16 11 16 25 12 40 OFF",
    "EXC2": "6k91 0 0 0 0 30 OFF 6k91 0 0 0 0 30 OFF",
    "EXC": "3k31 28 24 14 30 30 OFF",
    "IMG": "0 0 0 0.0 261 1.96 0.0",
    "EDI": "ON ST ST 0 0 0 0 0.0",
    "SON": "ON 0.6 0.8 0.0 ON 0.6 0.8 0.0",
    "AMP2": "5.0 5.0 5.0 5.0 5.0 5.0 5.0 5.0 ON 5.0 5.0 5.0 5.0 5.0 5.0 5.0 5.0 ON",
    "AMP": "5.0 5.0 5.0 5.0 5.0 5.0 5.0 5.0 ON",
    "DRV2": "50 20 20 0.0 100 6k9 0.0 197 0.0 3k0 50 20 20 0.0 100 6k9 0.0 197 0.0 3k0",
    "DRV": "25 20 28 -6.5 55 18k7 0.0 154 0.0 4k1",
    "PIT2": "0 -10 5.0 100 -50 100 0 10 6.9 100 50 15k8",
    "PIT": "0 0 5.0 52 15k8 100",
}
