# Use an official Python runtime as a parent image
FROM python:3.12-slim

RUN pip install poetry


# Copy only the dependency files first (for caching)
COPY pyproject.toml poetry.lock ./

# Install dependencies without creating a virtualenv inside the container
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Set the working directory in the container
WORKDIR /app

# Copy the rest of the application code to the working directory
COPY . .

# Command to run the app when the container starts
# Uvicorn is the server that runs FastAPI.
# The --host 0.0.0.0 makes the app accessible from outside the container.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
# CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
