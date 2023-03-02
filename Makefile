interactive: build
	docker run --rm -it --volume=${CURDIR}/pybravia:/app/pybravia --volume=${CURDIR}/scripts:/app/scripts --workdir=/app/ pybravia-dev bash

build:
	docker build -t pybravia-dev . 