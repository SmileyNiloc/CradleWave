# Use an official Python runtime as a parent image
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir poetry

# Copy only the dependency files first (for caching)
COPY pyproject.toml poetry.lock ./

# Install dependencies without creating a virtualenv inside the container
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Set the working directory in the container
# WORKDIR /ingestor

# Copy the rest of the application code to the working directory
COPY . .

# Command to run the app when the container starts
# Run the ingestor as a background worker (pure asyncio, no web framework)
CMD ["python", "ingestor.py"]
