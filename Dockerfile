FROM python:3.11-slim

# set our working directory
WORKDIR /app

#  create our entrypoint
COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

# install ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg

# install dependencies
COPY . .
RUN pip install --upgrade pip && pip install --no-cache-dir -r /app/requirements.txt

# run our code
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python", "hathor.py"]