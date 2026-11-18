"""Execute the actual Java MIME policy without substituting an Android picker."""
from pathlib import Path
import os
import shutil
import subprocess

import pytest


def test_shared_zip_and_history_json_declarations_select_their_actual_document_types(tmp_path):
    compiler = shutil.which('javac')
    if compiler is None and os.environ.get('JAVA_HOME'):
        candidate = Path(os.environ['JAVA_HOME']) / 'bin' / ('javac.exe' if os.name == 'nt' else 'javac')
        compiler = str(candidate) if candidate.is_file() else None
    if compiler is None:
        pytest.skip('The native build-host Java compiler is unavailable')
    source = Path(__file__).resolve().parents[2] / 'packaging/android/app/src/main/java/io/github/firebird55/gameimmersiontoolkit/AcceptedDocuments.java'
    proof = tmp_path / 'DocumentPolicyProof.java'
    proof.write_text('''package io.github.firebird55.gameimmersiontoolkit;
import java.util.Arrays;
public class DocumentPolicyProof {
  static void check(String[] input, String... expected) {
    if (!Arrays.equals(AcceptedDocuments.mimeTypes(input), expected)) throw new AssertionError();
  }
  public static void main(String[] args) {
    check(new String[]{".zip", "application/zip"}, "application/zip");
    check(new String[]{".json", "application/json"}, "application/json");
    check(new String[]{" .JSON, application/json "}, "application/json");
    check(new String[]{"application/x-zip-compressed", ".json"}, "application/zip", "application/json");
    for (String value : new String[]{"", "*/*", "application/*", "image/png", ".zip,image/png", "application/json; charset=utf-8", ".json,", "x".repeat(1025)}) check(new String[]{value});
    check(null);check(new String[0]);check(new String[]{null});check(new String[17]);
  }
}''', encoding='utf-8')
    subprocess.run([compiler, '-encoding', 'UTF-8', '-d', str(tmp_path), str(source), str(proof)], check=True, capture_output=True, timeout=30)
    executable = Path(compiler).with_name('java.exe' if os.name == 'nt' else 'java')
    subprocess.run([str(executable), '-cp', str(tmp_path), 'io.github.firebird55.gameimmersiontoolkit.DocumentPolicyProof'], check=True, capture_output=True, timeout=30)
