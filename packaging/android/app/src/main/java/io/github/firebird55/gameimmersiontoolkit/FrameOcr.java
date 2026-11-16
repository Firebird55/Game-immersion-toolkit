package io.github.firebird55.gameimmersiontoolkit;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Rect;
import com.chaquo.python.Python;
import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions;
import com.google.mlkit.vision.text.japanese.JapaneseTextRecognizerOptions;
import com.google.mlkit.vision.text.korean.KoreanTextRecognizerOptions;
import java.util.HashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONArray;
import org.json.JSONObject;

/** Bundled on-device OCR; one worker and only the newest waiting frame. */
public final class FrameOcr {
    private static final class Frame {
        final byte[] bytes;final long generation, sequence;final String locale;
        Frame(byte[] b, long g, long s, String l) { bytes=b;generation=g;sequence=s;locale=l; }
    }
    private final java.util.concurrent.ExecutorService worker = Executors.newSingleThreadExecutor();
    private final AtomicReference<Frame> pending = new AtomicReference<>();
    private final AtomicBoolean active = new AtomicBoolean(false);
    private final HashMap<String, TextRecognizer> models = new HashMap<>();
    public FrameOcr(Context context) { }
    public void submit(byte[] bytes, long generation, long sequence, String locale) {
        if (bytes.length == 0 || bytes.length > 10 * 1024 * 1024) throw new IllegalArgumentException();
        pending.set(new Frame(bytes, generation, sequence, locale));
        schedule();
    }
    private void schedule() {
        if (active.compareAndSet(false, true)) worker.execute(() -> {
            try {
                Frame frame;
                while ((frame = pending.getAndSet(null)) != null) recognize(frame);
            } finally {
                active.set(false);
                if (pending.get() != null) schedule();
            }
        });
    }
    private TextRecognizer model(String locale) {
        String script = locale.startsWith("zh") ? "zh" : locale.startsWith("ja") ? "ja" : locale.startsWith("ko") ? "ko" : "latin";
        TextRecognizer result = models.get(script);
        if (result == null) {
            switch (script) {
                case "zh": result = TextRecognition.getClient(new ChineseTextRecognizerOptions.Builder().build());break;
                case "ja": result = TextRecognition.getClient(new JapaneseTextRecognizerOptions.Builder().build());break;
                case "ko": result = TextRecognition.getClient(new KoreanTextRecognizerOptions.Builder().build());break;
                default: result = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
            }
            models.put(script, result);
        }
        return result;
    }
    private void recognize(Frame frame) {
        Bitmap bitmap = null;
        try {
            BitmapFactory.Options bounds = new BitmapFactory.Options();bounds.inJustDecodeBounds = true;
            BitmapFactory.decodeByteArray(frame.bytes, 0, frame.bytes.length, bounds);
            if (bounds.outWidth <= 0 || bounds.outHeight <= 0 || bounds.outWidth > 4096 || bounds.outHeight > 4096) return;
            bitmap = BitmapFactory.decodeByteArray(frame.bytes, 0, frame.bytes.length);
            if (bitmap == null) return;
            JSONObject result = recognizeBitmap(bitmap, frame.locale);
            Python.getInstance().getModule("backend.android_host").callAttr("accept_ocr", frame.generation, frame.sequence, result.toString());
        } catch (Exception error) {
            if (BuildConfig.DEBUG) android.util.Log.w("ToolkitAndroid", "A frame could not be recognized locally");
        } finally { if (bitmap != null) bitmap.recycle(); }
    }
    private synchronized JSONObject recognizeBitmap(Bitmap bitmap, String locale) throws Exception {
            Text text = Tasks.await(model(locale).process(InputImage.fromBitmap(bitmap, 0)), 30, TimeUnit.SECONDS);
            JSONArray blocks = new JSONArray();
            if (text.getTextBlocks().size() > 128) throw new IllegalArgumentException();
            for (Text.TextBlock block : text.getTextBlocks()) {
                Rect r = block.getBoundingBox();
                if (r == null || block.getText().length() > 8192) continue;
                JSONObject item = new JSONObject();item.put("text", block.getText());
                item.put("rect", new JSONArray(new int[]{r.left, r.top, r.right, r.bottom}));blocks.put(item);
            }
            JSONObject result = new JSONObject();result.put("width", bitmap.getWidth());
            result.put("height", bitmap.getHeight());result.put("blocks", blocks);
            return result;
    }
    public String authoredProbe() throws Exception {
        if (!BuildConfig.DEBUG) throw new IllegalStateException();
        Bitmap bitmap = Bitmap.createBitmap(1600, 240, Bitmap.Config.ARGB_8888);
        try {
            android.graphics.Canvas canvas = new android.graphics.Canvas(bitmap);
            canvas.drawColor(android.graphics.Color.BLACK);
            android.graphics.Paint paint = new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
            paint.setColor(android.graphics.Color.WHITE);paint.setTextSize(64);
            canvas.drawText("Follow the river beyond the bridge.", 40, 140, paint);
            return recognizeBitmap(bitmap, "en").toString();
        } finally {bitmap.recycle();}
    }
}
