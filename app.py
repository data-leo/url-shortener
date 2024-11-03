import os
from flask import Flask, redirect, request, jsonify, render_template_string
import string
import random
import psycopg2
from psycopg2.extras import DictCursor
from urllib.parse import urlparse

app = Flask(__name__)

# 환경 변수에서 데이터베이스 URL 가져오기
DATABASE_URL = os.getenv('DATABASE_URL')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:5000')

def get_db_connection():
    """PostgreSQL 데이터베이스 연결을 반환하는 함수"""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

def init_db():
    """데이터베이스 초기화"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS urls
                (id SERIAL PRIMARY KEY,
                 original_url TEXT NOT NULL,
                 short_code TEXT NOT NULL UNIQUE,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 clicks INTEGER DEFAULT 0)
            ''')

# HTML 템플릿 (이전과 동일)
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>URL 단축기</title>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            max-width: 800px; 
            margin: 0 auto; 
            padding: 20px;
        }
        .container { text-align: center; }
        input[type="text"] { 
            width: 80%; 
            padding: 10px; 
            margin: 10px 0;
        }
        button { 
            padding: 10px 20px; 
            background-color: #007bff; 
            color: white; 
            border: none; 
            cursor: pointer;
        }
        #result {
            margin-top: 20px;
            padding: 10px;
            border: 1px solid #ddd;
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>URL 단축 서비스</h1>
        <div>
            <input type="text" id="url" placeholder="단축할 URL을 입력하세요">
            <button onclick="shortenURL()">URL 단축하기</button>
        </div>
        <div id="result"></div>
    </div>

    <script>
        function shortenURL() {
            const url = document.getElementById('url').value;
            fetch('/shorten', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({url: url})
            })
            .then(response => response.json())
            .then(data => {
                const resultDiv = document.getElementById('result');
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = `
                    <p>원본 URL: ${data.original_url}</p>
                    <p>단축 URL: <a href="${data.short_url}" target="_blank">${data.short_url}</a></p>
                `;
            })
            .catch(error => {
                console.error('Error:', error);
                alert('URL 단축 중 오류가 발생했습니다.');
            });
        }
    </script>
</body>
</html>
'''

def generate_short_code(length=6):
    """무작위 단축 코드 생성"""
    characters = string.ascii_letters + string.digits
    while True:
        code = ''.join(random.choice(characters) for _ in range(length))
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT 1 FROM urls WHERE short_code = %s', (code,))
                if not cur.fetchone():
                    return code

def is_valid_url(url):
    """URL 유효성 검사"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

@app.route('/')
def home():
    """홈페이지 렌더링"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/shorten', methods=['POST'])
def shorten_url():
    """URL 단축 API"""
    try:
        data = request.get_json()
        original_url = data.get('url')
        
        if not original_url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not is_valid_url(original_url):
            return jsonify({'error': 'Invalid URL'}), 400

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                # 기존 URL 확인
                cur.execute('SELECT short_code FROM urls WHERE original_url = %s', 
                          (original_url,))
                existing = cur.fetchone()
                
                if existing:
                    short_code = existing['short_code']
                else:
                    short_code = generate_short_code()
                    cur.execute(
                        'INSERT INTO urls (original_url, short_code) VALUES (%s, %s)',
                        (original_url, short_code)
                    )

        short_url = f"{BASE_URL}/{short_code}"
        return jsonify({
            'original_url': original_url,
            'short_url': short_url
        })
    except Exception as e:
        app.logger.error(f"Error in shorten_url: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/<short_code>')
def redirect_to_url(short_code):
    """단축 URL 리다이렉션"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                # 클릭 수 증가와 함께 URL 가져오기
                cur.execute(
                    'UPDATE urls SET clicks = clicks + 1 WHERE short_code = %s RETURNING original_url',
                    (short_code,)
                )
                result = cur.fetchone()

        if result is None:
            return jsonify({'error': 'URL not found'}), 404
        
        return redirect(result['original_url'])
    except Exception as e:
        app.logger.error(f"Error in redirect_to_url: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    init_db()
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)