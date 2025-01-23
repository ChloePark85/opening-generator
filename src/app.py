import streamlit as st
import requests
import logging
import io
import os
import tempfile
from pydub import AudioSegment
from pydub.generators import Sine
from elevenlabs import ElevenLabs
from datetime import datetime

# 로깅 설정
logging.basicConfig(level=logging.INFO)

SWOOSH_EFFECT_URL = "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/Swooshes%2C+Whoosh%2C+Organic%2C+Wind%2C+Soft%2C+Normal+02+SND55378+6.wav"

# Streamlit Secrets에서 TTS 설정 가져오기
try:
    ELEVENLABS_API_KEY = st.secrets["ELEVENLABS_API_KEY"]
except Exception as e:
    st.error("Elevenlabs API 키 설정이 필요합니다. Streamlit Secrets를 확인해주세요.")
    st.stop()

# 배경음악 URL들
BGM_URLS = {
    "로맨스": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/romance4.mp3",
    "스릴러": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/Alon+Ohana+-+Narrow+View.mp3",
    "동화": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/dream.mp3",
    "뉴스": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/Ariel+Shalom++-+Eternal+Echoes.mp3"
}

VOICE_IDS = {
    "여성 화자": "kLtVxhs5O2bJqOBpeTV6",  # Elevenlabs 여성 보이스 ID
    "남성 화자": "3MMlKavlOQfPfUwRwYNI"    # Elevenlabs 남성 보이스 ID
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

def is_english(text):
    """텍스트가 영어인지 확인하는 함수"""
    # 영어 알파벳, 숫자, 공백, 문장부호만 포함되어 있는지 확인
    return all(ord(char) < 128 for char in text.replace(' ', '').replace('.', '').replace(',', '').replace('!', '').replace('?', ''))

def text_to_speech(text, voice_id, speed=1.0):
    """Elevenlabs TTS API를 사용하여 음성을 생성하는 함수"""
    try:
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        
        # 제목 끝에 마침표 추가하고, 영어/한글 구분하여 제작사 소개 텍스트 구성
        title_with_period = f"{text}..." if not text.endswith('.') else text
        outro = "    produced by nadio." if is_english(text) else "    제작, 나디오"
        full_text = f"{title_with_period}\n\n{outro}"
        
        # 음성 생성
        audio_stream = client.text_to_speech.convert(
            voice_id=voice_id,
            text=full_text,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128"
        )
        
        # 스트림을 바이트로 변환
        if hasattr(audio_stream, 'read'):
            audio_bytes = audio_stream.read()
        elif isinstance(audio_stream, (bytes, bytearray)):
            audio_bytes = audio_stream
        else:
            audio_bytes = b''.join(chunk for chunk in audio_stream)
        
        # 임시 파일로 저장 (mp3 형식으로)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        temp_file.write(audio_bytes)
        temp_file.close()
        
        return temp_file.name
        
    except Exception as e:
        st.error(f"TTS 변환 중 오류가 발생했습니다: {str(e)}")
        return None

def process_audio_files(bgm_path, tts_path, swoosh_path):
    """배경음악, 효과음, TTS 음성을 결합하는 함수"""
    try:
        # 오디오 파일 불러오기
        bgm = AudioSegment.from_mp3(bgm_path)
        tts = AudioSegment.from_mp3(tts_path)
        swoosh = AudioSegment.from_wav(swoosh_path)
        
        # 시작 6초 동안의 배경음악 (원본 볼륨)
        initial_duration = 6000  # 6초로 변경
        initial_bgm = bgm[:initial_duration]
        
        # 효과음 볼륨 조정
        swoosh = swoosh + 3
        
        # TTS에 페이드인 적용
        tts = tts.fade_in(50)
        
        # 효과음이 재생되는 동안의 배경음악
        bgm_during_swoosh = bgm[initial_duration:initial_duration + len(swoosh)]
        bgm_during_swoosh = bgm_during_swoosh.fade(
            from_gain=0,
            to_gain=-10,
            start=0,
            duration=len(swoosh)
        )
        
        # TTS와 함께 깔릴 배경음악
        bgm_during_tts = bgm[initial_duration + len(swoosh):initial_duration + len(swoosh) + len(tts)] - 10
        
        # TTS 이후 배경음악
        post_tts_duration = 2500  # 2.5초
        fade_duration = 3000      # 3초
        total_length = initial_duration + len(swoosh) + len(tts)
        bgm_after_tts = bgm[total_length:total_length + post_tts_duration] - 10
        bgm_fadeout = bgm[total_length + post_tts_duration:total_length + post_tts_duration + fade_duration] - 10
        bgm_fadeout = bgm_fadeout.fade_out(duration=fade_duration)
        
        # 순차적으로 오디오 결합
        combined = initial_bgm
        
        # 효과음과 배경음악 오버레이
        swoosh_segment = bgm_during_swoosh.overlay(swoosh)
        combined = combined + swoosh_segment
        
        # TTS와 배경음악 오버레이
        tts_with_bgm = bgm_during_tts.overlay(tts)
        combined = combined + tts_with_bgm
        
        # TTS 이후 배경음악 추가
        combined = combined + bgm_after_tts + bgm_fadeout
        
        # CBR MP3로 저장
        output_path = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3').name
        combined.export(
            output_path,
            format='mp3',
            bitrate='192k',
            parameters=[
                "-ar", "44100",
                "-ac", "2",
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                "-f", "mp3"
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
        col1, col2 = st.columns(2)
        
        with col1:
            title = st.text_input("작품명을 입력하세요")
            bgm_selection = st.selectbox(
                "배경음악을 선택하세요",
                list(BGM_URLS.keys())
            )
            
        with col2:
            voice_selection = st.selectbox(
                "화자를 선택하세요",
                list(VOICE_IDS.keys())
            )
            speed = st.slider(
                "음성 속도",
                min_value=0.5,
                max_value=2.0,
                value=1.0,
                step=0.1
            )
        
        submitted = st.form_submit_button("오프닝 생성", use_container_width=True)
    
    if submitted and title:
        with st.spinner('오프닝 생성 중...'):
            # 필요한 모든 오디오 파일 다운로드
            temp_files = []
            
            # 배경음악 다운로드
            response = requests.get(BGM_URLS[bgm_selection])
            if response.status_code == 200:
                bgm_path = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3').name
                with open(bgm_path, 'wb') as f:
                    f.write(response.content)
                temp_files.append(bgm_path)
            
            # 효과음 다운로드
            response = requests.get(SWOOSH_EFFECT_URL)
            if response.status_code == 200:
                swoosh_path = tempfile.NamedTemporaryFile(delete=False, suffix='.wav').name
                with open(swoosh_path, 'wb') as f:
                    f.write(response.content)
                temp_files.append(swoosh_path)
            
            # TTS 생성
            tts_path = text_to_speech(title, VOICE_IDS[voice_selection], speed)
            if tts_path:
                temp_files.append(tts_path)
            
            if all([bgm_path, swoosh_path, tts_path]):
                # 오디오 처리
                final_path = process_audio_files(bgm_path, tts_path, swoosh_path)
                
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
                    
                    temp_files.append(final_path)
            
            # 임시 파일 삭제
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)

if __name__ == "__main__":
    main()