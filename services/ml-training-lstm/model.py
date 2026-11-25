"""Issue #85의 NOx 60분 진입 분류용 LSTM 모델."""
from adapter import SLOT_COLUMNS


def build_model():
    """6슬롯 입력에 대한 이진 분류 모델을 컴파일한다. 행과 클래스에는 동일 가중치를 사용한다."""
    from tensorflow import keras

    model = keras.Sequential(
        [
            keras.Input(shape=(len(SLOT_COLUMNS), 1), dtype="float32"),
            keras.layers.LSTM(32),
            keras.layers.Dense(1, activation="sigmoid"),
        ],
        name="nox_lstm",
    )
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss=keras.losses.BinaryCrossentropy(),
        metrics=[keras.metrics.AUC(curve="PR", name="pr_auc")],
    )
    return model
