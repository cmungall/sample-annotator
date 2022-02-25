RUN = poetry run

.PHONY: test clean all

all: clean test examples/outputs/report.tsv

# ---------------------------------------
# Test runner
# ----------------------------------------
test:
	$(RUN) pytest 2>&1 | tee logs/tests.log
	$(RUN) pytest -sv tests/test_capitalization.py


clean:
	find examples -name "*report.tsv" -exec rm -rf {} \;
	rm -rf assets/*tsv
	rm -rf assets/*bak
	rm -rf bin/*jar
	rm -rf downloads/*
	rm -rf examples/outputs/*
	rm -rf logs/*log
	rm -rf target/*

examples/outputs/report.tsv: examples/gold.json
	$(RUN) annotate-sample -R $@ $<

downloads/mixs6_core.tsv:
	curl -L -s 'https://docs.google.com/spreadsheets/d/1QDeeUcDqXes69Y2RjU2aWgOpCVWo5OVsBX9MKmMqi_o/export?format=tsv&gid=178015749' > $@


biosample_sqlite_file = ~/biosample_basex_data_good_subset.db

examples/outputs/non_attribute_metadata_sel_envs_partial.tsv:
	$(RUN) sqlite_client_cli \
		--sqlite_path $(biosample_sqlite_file) \
		--query "select * from non_attribute_metadata_sel_envs limit 9" \
		--tsv_out $@

rel_to_oxygen_example: downloads/mixs6_core.tsv
	$(RUN) rel_to_oxygen_example \
		--sqlite_path $(biosample_sqlite_file) \
		--mixs_core_path $<


bin/robot.jar:
	curl -s https://api.github.com/repos/ontodev/robot/releases/latest  | grep 'browser_download_url.*\.jar"' |  cut -d : -f 2,3 | tr -d \" | wget -O $@ -i -

downloads/bibo.owl:
	# --location (-L) pursues redirects
	curl --location https://raw.githubusercontent.com/structureddynamics/Bibliographic-Ontology-BIBO/master/bibo.owl -o $@

assets/bibo_DocumentStatus.tsv: downloads/bibo.owl bin/robot.jar
	java -jar bin/robot.jar query --input $< --query sparql/bibo_DocumentStatus.sparql $@
	sed --in-place=.bak 's/^\?//' $@