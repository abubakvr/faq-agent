# Nithub QA Chatbot API

A FastAPI-based question-answering system for Nithub that uses RAG (Retrieval-Augmented Generation) to answer questions based on a curated knowledge base. The system combines semantic search using HuggingFace embeddings with Google Gemini for natural language generation.

## Features

- 🤖 **RAG-based QA System**: Retrieves relevant information from a CSV knowledge base and generates answers
- 🔍 **Semantic Search**: Uses HuggingFace sentence-transformers for embedding-based document retrieval
- 💬 **LLM Integration**: Powered by Google Gemini for natural answer generation
- 💾 **Conversation Logging**: Stores all questions and answers in PostgreSQL
- 🐳 **Dockerized**: Fully containerized setup with docker-compose
- 📊 **Vector Database**: Uses ChromaDB for efficient similarity search

## Tech Stack

- **FastAPI**: REST API framework
- **Google Gemini**: Large Language Model for answer generation
- **HuggingFace Embeddings**: `sentence-transformers/all-MiniLM-L6-v2` for embeddings
- **ChromaDB**: Vector database for storing and querying embeddings
- **PostgreSQL**: Relational database for conversation history
- **LangChain**: Framework for building LLM applications

## Prerequisites

- Python 3.11+
- Docker and Docker Compose (for containerized deployment)
- Google API Key with Gemini API access
- PostgreSQL (if running locally, or use Docker)

## Project Structure

```
.
├── main.py                 # FastAPI application and API endpoints
├── vector.py              # Vector store initialization and embeddings
├── database.py            # PostgreSQL models and database setup
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker image definition
├── docker-compose.yml    # Docker Compose configuration
├── nithub_question.csv   # Knowledge base Q&A data
├── .env                  # Environment variables (create this)
└── README.md            # This file
```

## Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd ollama-agent
```

### 2. Create Environment File

Create a `.env` file in the project root:

```bash
# Google API Configuration
GOOGLE_API_KEY=your_google_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Database Configuration
DB_HOST=localhost
DB_PORT=5435
DB_NAME=nitchatbot
DB_USER=nituser
DB_PASSWORD=your_db_password_here
```

### 3. Local Development Setup

#### Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

#### Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### Run Locally

```bash
python -m uvicorn main:app --reload --port 8080
```

The API will be available at `http://localhost:8080`

### 4. Docker Deployment

#### Build and Start Services

```bash
docker compose up --build
```

This will:

- Start PostgreSQL on port 5435
- Build and start the API on port 8080
- Initialize the vector database with embeddings from `nithub_question.csv`

#### Stop Services

```bash
docker compose down
```

To remove volumes (including database data):

```bash
docker compose down -v
```

## API Endpoints

### `POST /ask`

Ask a question about Nithub.

**Request Body:**

```json
{
  "question": "What is Nithub and where is it located?"
}
```

**Response:**

```json
{
  "answer": "Nithub is an innovation hub dedicated to building Africa's future... We are located at 6 Commercial Road, University of Lagos, Lagos, Nigeria."
}
```

### `GET /`

Health check endpoint.

**Response:**

```json
{
  "message": "Nithub QA API is running!"
}
```

## Usage Examples

### Using curl

```bash
curl -X POST "http://localhost:8080/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "What are your opening hours?"}'
```

### Using the provided REST file

The `rest.http` file contains example requests that can be used with REST Client extensions in VS Code.

## How It Works

1. **Question Reception**: User sends a question via the `/ask` endpoint
2. **Semantic Search**: The question is embedded and matched against the vector database (ChromaDB) to find the top 5 most relevant Q&A pairs from the CSV
3. **Context Building**: Retrieved documents are formatted as context for the LLM
4. **Answer Generation**: Google Gemini generates an answer based on the retrieved context and follows the prompt instructions
5. **Storage**: The question and answer are saved to PostgreSQL for conversation history
6. **Response**: The generated answer is returned to the user

## Configuration

### Environment Variables

| Variable         | Description                                     | Required |
| ---------------- | ----------------------------------------------- | -------- |
| `GOOGLE_API_KEY` | Google API key for Gemini                       | Yes      |
| `GEMINI_MODEL`   | Gemini model name (default: `gemini-2.5-flash`) | No       |
| `DB_HOST`        | PostgreSQL host                                 | Yes      |
| `DB_PORT`        | PostgreSQL port                                 | Yes      |
| `DB_NAME`        | Database name                                   | Yes      |
| `DB_USER`        | Database user                                   | Yes      |
| `DB_PASSWORD`    | Database password                               | Yes      |

### Embedding Model

The system uses `sentence-transformers/all-MiniLM-L6-v2` which:

- Produces 384-dimensional embeddings
- Is optimized for semantic search
- Runs entirely locally (no API calls needed)
- First download is ~80MB, then cached

### Knowledge Base

The `nithub_question.csv` file should have the following structure:

```csv
Question,Answer
"What is Nithub?","Nithub is an innovation hub..."
"Where is Nithub located?","We are located at..."
```

## Database Schema

### Conversations Table

Stores all questions and answers:

| Column       | Type     | Description      |
| ------------ | -------- | ---------------- |
| `id`         | Integer  | Primary key      |
| `question`   | Text     | User's question  |
| `answer`     | Text     | Generated answer |
| `created_at` | DateTime | Timestamp        |

## Troubleshooting

### Vector Database Dimension Mismatch

If you get an error about embedding dimensions, delete the Chroma database:

```bash
# Locally
rm -rf chrome_langchain_db_nithub

# Docker
docker compose exec api rm -rf /app/chrome_langchain_db_nithub
docker compose restart api
```

### Database Connection Issues

- Ensure PostgreSQL is running
- Check that credentials in `.env` match your database
- Verify the database exists: `docker compose exec postgres psql -U nituser -d nitchatbot`

### Missing Embeddings

The first request will take longer as it downloads the HuggingFace model. Subsequent requests are fast.

## Development

### Running Tests

```bash
# Install test dependencies (if any)
pip install pytest pytest-asyncio httpx

# Run tests
pytest
```

### Code Structure

- `main.py`: FastAPI routes and LLM integration
- `vector.py`: Embeddings and vector store setup
- `database.py`: SQLAlchemy models and database connection
- `vector.py`: Handles document embedding and retrieval

## License

[Add your license here]

## Contributing

[Add contributing guidelines here]

## Support

For issues or questions, please contact [your contact information]
