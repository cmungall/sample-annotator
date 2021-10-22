from enum import Enum
from typing import Optional

from pydantic import BaseModel
import pydantic
from pydantic.dataclasses import dataclass
from nmdc_schema.nmdc import Study

from fastapi import FastAPI, Query

from sample_annotator.sample_annotator import SampleAnnotator, AnnotationReport, SAMPLE

#Study = pydantic.dataclasses.dataclass(Study, init=False)

annotator = SampleAnnotator()

class ModelName(str, Enum):
    alexnet = "alexnet"
    resnet = "resnet"
    lenet = "lenet"

class Item(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    tax: Optional[float] = None

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.post("/annotate/", response_model=AnnotationReport)
async def annotate_sample(sample: SAMPLE):
    report = annotator.annotate(sample)
    return report

@app.post("/items/", response_model=Item)
async def create_item(item: Item):
    item_dict = item.dict()
    if item.tax:
        price_with_tax = item.price + item.tax
        item_dict.update({"price_with_tax": price_with_tax})
    return item_dict

#@app.get("/studies/{id}", response_model=Study)
#async def get_study(id: str):
#    return Study()

@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}

@app.get("/items/")
async def read_items(
        q: Optional[str] = Query(None, min_length=3, max_length=50, regex="^fixedquery$")
):
    results = {"items": [{"item_id": "Foo"}, {"item_id": "Bar"}]}
    if q:
        results.update({"q": q})
    return results

@app.get("/models/{model_name}")
async def get_model(model_name: ModelName):
    if model_name == ModelName.alexnet:
        return {"model_name": model_name, "message": "Deep Learning FTW!"}

    if model_name.value == "lenet":
        return {"model_name": model_name, "message": "LeCNN all the images"}

    return {"model_name": model_name, "message": "Have some residuals"}
