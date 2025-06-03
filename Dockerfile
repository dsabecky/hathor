FROM python:3.11-slim

# create our user
RUN adduser --disabled-password hathor
WORKDIR /app

#  create our entrypoint
COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

# set file permissions and install dependencies
COPY --chown=hathor:hathor . .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# set our user
USER hathor

# run our code
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python", "hathor.py"]