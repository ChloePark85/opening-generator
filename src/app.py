import streamlit as st
import requests
import logging
import io
import os
import tempfile
from pydub import AudioSegment
from pydub.generators import Sine

# 로깅 설정
logging.basicConfig(level=logging.INFO)

# Streamlit Secrets에서 TTS 설정 가져오기
try:
    TTS_API_ENDPOINT = st.secrets["TTS_API_ENDPOINT"]
    TTS_VOICE_ID = st.secrets["TTS_VOICE_ID"]
except Exception as e:
    st.error("TTS API 설정이 필요합니다. Streamlit Secrets를 확인해주세요.")
    st.stop()

# 배경음악 URL들
BGM_URLS = {
    "로맨스": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/romance1.mp3",
    "스릴러": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/Alon+Ohana+-+Narrow+View.mp3",
    "동화": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/dream.mp3",
    "뉴스": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/Ariel+Shalom++-+Eternal+Echoes.mp3"
}

def download_bgm(url):
    """배경음악 다운로드"""
    try:
        response = requests.get(url)
        if response.status_code == 200:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
            temp_file.write(response.content)
            temp_file.close()
            return temp_file.name
        else:
            st.error(f"배경음악 다운로드 실패: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"배경음악 다운로드 중 오류 발생: {str(e)}")
        return None

def text_to_speech(text, speed=1.0):
    """TTS API를 호출하여 음성을 생성하는 함수"""
    try:
        payload = {
            "mode": "openfont",
            "sentences": [
                {
                    "type": "text",
                    "text": text,
                    "version": "0",
                    "voice_id": TTS_VOICE_ID,
                    "options": {
                        "speed": speed
                    }
                }
            ]
        }
        
        logging.info("Sending TTS request")
        response = requests.post(
            TTS_API_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
            temp_file.write(response.content)
            temp_file.close()
            return temp_file.name
        else:
            st.error(f"TTS API 오류: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        st.error(f"TTS 변환 중 오류가 발생했습니다: {str(e)}")
        return None

def process_audio_files(bgm_path, tts_path):
    """배경음악과 TTS 음성을 결합하는 함수"""
    try:
        # 오디오 파일 불러오기
        bgm = AudioSegment.from_mp3(bgm_path)
        tts = AudioSegment.from_wav(tts_path)
        
        # 시작 5초 동안의 배경음악 (원본 볼륨)
        initial_bgm = bgm[:5000]
        
        # TTS 길이 + 5초 만큼의 배경음악 준비 (볼륨 낮춤)
        soft_bgm = bgm[5000:5000 + len(tts) + 5000] - 20  # -20dB로 볼륨 낮춤
        
        # TTS 시작 전 5초
        combined = initial_bgm
        
        # TTS와 낮은 볼륨의 배경음악 오버레이
        tts_with_bgm = soft_bgm[:len(tts)].overlay(tts)
        combined = combined + tts_with_bgm
        
        # TTS 이후 5초 동안 배경음악 페이드아웃
        final_bgm = soft_bgm[len(tts):len(tts) + 5000].fade_out(duration=5000)
        combined = combined + final_bgm
        
        # CBR MP3로 저장 (192kbps, 44.1kHz)
        output_path = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3').name
        combined.export(
            output_path,
            format='mp3',
            bitrate='192k',
            parameters=[
                "-ar", "44100",      # 샘플링 레이트 44.1kHz
                "-ac", "2",          # 스테레오
                "-c:a", "libmp3lame", # MP3 인코더
                "-b:a", "192k",      # 고정 비트레이트 192kbps
                "-f", "mp3"          # 출력 포맷
            ]
        )
        
        return output_path
    except Exception as e:
        st.error(f"오디오 처리 중 오류가 발생했습니다: {str(e)}")
        return None

def main():
    st.title("📚 이어가다 오디오북 오프닝 생성기")
    
    # 입력 폼
    with st.form("opening_form"):
        title = st.text_input("작품명을 입력하세요")
        
        bgm_selection = st.selectbox(
            "배경음악을 선택하세요",
            list(BGM_URLS.keys())
        )
        
        submitted = st.form_submit_button("오프닝 생성", use_container_width=True)
    
    if submitted and title:
        with st.spinner('오프닝 생성 중...'):
            # 배경음악 다운로드
            bgm_path = download_bgm(BGM_URLS[bgm_selection])
            
            # TTS 생성
            opening_text = f"{title}. 제작, 나디오."
            tts_path = text_to_speech(opening_text)
            
            if bgm_path and tts_path:
                # 오디오 처리
                final_path = process_audio_files(bgm_path, tts_path)
                
                if final_path:
                    # 결과 재생
                    with open(final_path, 'rb') as audio_file:
                        audio_data = audio_file.read()
                        st.audio(audio_data, format='audio/mp3')
                        
                        # 다운로드 버튼
                        st.download_button(
                            label="오프닝 오디오 다운로드",
                            data=audio_data,
                            file_name=f"opening_{title}.mp3",
                            mime="audio/mp3",
                            use_container_width=True
                        )
                    
                    # 임시 파일 삭제
                    os.unlink(final_path)
                    os.unlink(bgm_path)
                    os.unlink(tts_path)

if __name__ == "__main__":
    main()