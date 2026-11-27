"""LN2의 시계열·통계/시간 Feature 결합 모델."""
from normalization import INPUT_SHAPE
from ln2_data import FEATURE_COLUMNS


def build_model():
    from tensorflow import keras

    sequence = keras.Input(shape=INPUT_SHAPE, dtype="float32", name="sequence")
    features = keras.Input(shape=(len(FEATURE_COLUMNS),), dtype="float32", name="features")
    sequence_out = keras.layers.LSTM(32)(sequence)
    feature_out = keras.layers.Dense(8, activation="relu")(features)
    fused = keras.layers.Concatenate()([sequence_out, feature_out])
    fused = keras.layers.Dense(16, activation="relu")(fused)
    probability = keras.layers.Dense(1, activation="sigmoid")(fused)
    model = keras.Model(inputs={"sequence": sequence, "features": features}, outputs=probability, name="LN2")
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss=keras.losses.BinaryCrossentropy(),
        metrics=[keras.metrics.AUC(curve="PR", name="pr_auc")],
    )
    return model
