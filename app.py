from fastapi import FastAPI
from init_db import init_database
import joblib
import os
import random

app = FastAPI()

MODEL_PATH = "model.pkl"

# Check and load model
model = None

if os.path.exists(MODEL_PATH):
    try:
        model = joblib.load(MODEL_PATH)
        print("Model loaded successfully!")
    except Exception as e:
        print("Model exists but could not be loaded:", e)
else:
    print("model.pkl is not available!")

@app.on_event("startup")
def startup_event():

    init_database()



@app.get("/")
def home():
    if model is not None:
        return {
            "message": "Model server is running",
            "model_available": True
        }
    else:
        return {
            "message": "Model server is running, but model is not available",
            "model_available": False
        }


@app.post("/predict")
def predict(data: dict):

    # if model is None:
    #     return {
    #         "error": "Model is not available",
    #         "prediction": None
    #     }

    # features = [[
    #     data["feature1"],
    #     data["feature2"],
    #     data["feature3"]
    # ]]

   # prediction = model.predict(features) 
    prediction = random.random() #! for demo

    return {
        "prediction": prediction
    }