FROM apify/actor-python-playwright:3.11
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
COPY . ./

CMD ["python3", "main.py"]
