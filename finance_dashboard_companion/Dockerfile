ARG BUILD_FROM
FROM $BUILD_FROM

# Install bash for run.sh
RUN apk add --no-cache bash

# Copy add-on files
COPY run.sh /run.sh
COPY payload /payload

RUN chmod a+x /run.sh

CMD ["/run.sh"]
