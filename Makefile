
all: $(SAMPLE_SCHEMA_JSON)
RUN = pipenv run
SAMPLE_SCHEMA_YAML = sample_annotator/model/schema/mixs.yaml
SAMPLE_SCHEMA_JSON = sample_annotator/model/schema/mixs.json

$(SAMPLE_SCHEMA_YAML):
	$(RUN) gen-yaml --mergeimports --no-metadata ../mixs-source/src/schema/mixs.yaml > $@.tmp && mv $@.tmp $@

$(SAMPLE_SCHEMA_JSON): $(SAMPLE_SCHEMA_YAML)
	 ./utils/yaml2json.py $< > $@

# ---------------------------------------
# Test runner
# ----------------------------------------
test:
	pipenv install --dev
	pipenv run python -m unittest

app:
	$(RUN) uvicorn sample_annotator.app.main:app --reload
