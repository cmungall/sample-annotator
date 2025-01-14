# review and fix readmes and poetry dependencies

MAX_STUDIES=70000 # 2025-01

.PHONY: load-gold-biosamples-into-mongo

downloads/goldData.xlsx:
	wget -O $@ "https://gold.jgi.doe.gov/download?mode=site_excel"

local/gold-studies.tsv: downloads/goldData.xlsx
	poetry run python sample_annotator/file_utils/xlsx_to_tsv.py \
		--excel-file $< \
		--sheet-name Study \
		--output-file $@

local/gold-study-ids.txt: local/gold-studies.tsv
	# without the grep filter, this introduces some noise (non-id rows)
	tail -n +2 $< | cut -f 1 | sort | grep 'Gs' > $@

local/gold-study-ids-subset.txt: local/gold-study-ids.txt
	head -n $(MAX_STUDIES) $< > $@

local/gold-cache.json: local/gold-study-ids-subset.txt
	# ~ 3 seconds/uncached study
	# GOLD has ~ 63k studies
	# < 2 days to fetch all studies ?
	poetry run python sample_annotator/clients/gold_client.py \
		--verbose \
		fetch-studies \
		--output-format json \
		--output $@ \
		--include-biosamples \
		--authentication-file config/gold-key.txt \
		$<

load-gold-biosamples-into-mongo: local/gold-study-ids-subset.txt
	# 		--purge-mongodb
	# 		--purge-diskcache
	poetry run python sample_annotator/gold_to_mongo.py \
		--authentication-file config/gold-key.txt \
		--mongo-db-name gold_metadata \
		--study-ids-file $<

#.PHONY: split-out-gold-biosamples
#split-out-gold-biosamples: local/gold-cache.json
#	poetry run python sample_annotator/file_utils/split_out_gold_biosamples.py \
#		--input-file $< \
#		--study-output-file local/gold-studies-only.json \
#		--biosample-output-file local/gold-biosamples-only.json \
#		--project-output-file local/gold-projects-only.json \
#		--remove-contacts \
#		--remove-nulls

local/ecosystems_and_triads.tsv:
	poetry run python sample_annotator/ecosystems_and_triads_from_mongo.py \
		--host localhost \
		--port 27017 \
		--db-name gold_metadata \
		--collection-name biosamples \
		--output-file $@


local/seq_projects.tsv:
	poetry run python sample_annotator/seq_projects_from_mongo.py \
		--host localhost \
		--port 27017 \
		--db-name gold_metadata \
		--collection-name projects \
		--output-file $@

