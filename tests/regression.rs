use age::x25519;
use serde_json::json;
use shared_video_transcriber::{
    browser::{auth_state, AuthState},
    media::{extract_url, parse_whisper, select_video},
    profile::{decrypt_archive, encrypt_archive},
};
use std::fs;

#[test]
fn accepts_douyin_share_text_only() {
    assert_eq!(
        extract_url("3.24 分享 https://v.douyin.com/abc123/ 复制打开抖音").unwrap(),
        "https://v.douyin.com/abc123/"
    );
    assert_eq!(
        extract_url("douyin.com/video/123456").unwrap(),
        "https://douyin.com/video/123456"
    );
    for value in [
        "https://youtube.com/watch?v=a",
        "https://bilibili.com/video/a",
        "https://evildouyin.com/video/a",
        "https://douyin.com.evil.test/video/1",
        "https://evil.test/v.douyin.com/abc/",
    ] {
        assert!(extract_url(value).is_err(), "must reject {value}");
    }
}

#[test]
fn login_requires_authenticated_self_response() {
    assert_eq!(
        auth_state(&json!({"status_code":0,"user":{"uid":"123"}})),
        AuthState::Valid
    );
    assert_eq!(
        auth_state(&json!({"status_code":0,"user":{"uid":"0"}})),
        AuthState::Unknown
    );
    assert_eq!(auth_state(&json!({"status_code":8})), AuthState::Expired);
    assert_eq!(
        auth_state(&json!({"cookies":["sessionid"]})),
        AuthState::Unknown
    );
}

#[test]
fn chooses_progressive_audio_video_instead_of_silent_dash() {
    let value = json!({"desc":"测试","video":{"bit_rate":[
        {"format":"dash","bit_rate":10,"play_addr":{"url_list":["https://cdn.test/silent"]}},
        {"format":"mp4","bit_rate":300,"play_addr":{"url_list":["https://cdn.test/high"]}},
        {"format":"mp4","bit_rate":100,"play_addr":{"url_list":["https://cdn.test/low"]}}
    ]}});
    assert_eq!(
        select_video(&value).unwrap(),
        ("https://cdn.test/low".into(), "测试".into())
    );
}

#[test]
fn whisper_millisecond_offsets_are_converted_once() {
    let value = json!({"result":{"language":"zh"},"transcription":[{"offsets":{"from":1230,"to":4560},"text":" 你好 "}]});
    let result = parse_whisper(&value, "source", "title").unwrap();
    assert_eq!(result.segments[0].start, 1.23);
    assert_eq!(result.segments[0].end, 4.56);
    assert_eq!(result.text, "你好");
    assert!(parse_whisper(
        &json!({"result":{"language":"zh"},"transcription":[]}),
        "",
        ""
    )
    .is_err());
}

#[test]
fn full_profile_roundtrip_preserves_ini_databases_and_caches() {
    let work = tempfile::tempdir().unwrap();
    let source = work.path().join("source");
    fs::create_dir_all(source.join("user-data/Default/Cache")).unwrap();
    fs::create_dir_all(source.join("user-data/Default/IndexedDB")).unwrap();
    for (name, contents) in [
        ("browser.ini", "config"),
        ("user-data/Default/Cookies", "cookies"),
        ("user-data/Default/Cache/entry", "cached"),
        ("user-data/Default/IndexedDB/data", "indexed"),
    ] {
        fs::write(source.join(name), contents).unwrap();
    }
    fs::write(source.join("user-data/SingletonLock"), "runtime").unwrap();
    let key = x25519::Identity::generate();
    let encrypted = work.path().join("profile.age");
    encrypt_archive(&source, &encrypted, &key).unwrap();
    let destination = work.path().join("restored");
    fs::create_dir(&destination).unwrap();
    decrypt_archive(&encrypted, &destination, &key).unwrap();
    assert_eq!(
        fs::read(destination.join("browser.ini")).unwrap(),
        b"config"
    );
    assert_eq!(
        fs::read(destination.join("user-data/Default/Cache/entry")).unwrap(),
        b"cached"
    );
    assert_eq!(
        fs::read(destination.join("user-data/Default/IndexedDB/data")).unwrap(),
        b"indexed"
    );
    assert!(!destination.join("user-data/SingletonLock").exists());
    assert!(decrypt_archive(
        &encrypted,
        &work.path().join("wrong-key"),
        &x25519::Identity::generate()
    )
    .is_err());
    let mut damaged = fs::read(&encrypted).unwrap();
    let end = damaged.len() - 1;
    damaged[end] ^= 1;
    fs::write(&encrypted, damaged).unwrap();
    let rejected = work.path().join("damaged");
    fs::create_dir(&rejected).unwrap();
    assert!(decrypt_archive(&encrypted, &rejected, &key).is_err());
    assert_eq!(fs::read_dir(rejected).unwrap().count(), 0);
}
