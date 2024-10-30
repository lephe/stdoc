BUNDLES := links-html links-nohtml

test: $(BUNDLES:%=test-%)

define mkrules_bundle
all-$1:
	(cd $1; env PYTHONPATH="../.." python -m stdoc .)

test-$1: all-$1
	(cd $1; diff -r _www_ref _www -u --color=always)

.PHONY: all-$1 test-$1
endef
$(foreach B,$(BUNDLES),$(eval $(call mkrules_bundle,$(B))))

.PHONY: all test
