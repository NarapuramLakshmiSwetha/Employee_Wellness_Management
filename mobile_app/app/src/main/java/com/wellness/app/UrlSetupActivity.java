package com.wellness.app;

import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.util.Patterns;
import android.widget.Button;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import com.google.android.material.textfield.TextInputEditText;

public class UrlSetupActivity extends AppCompatActivity {

    private TextInputEditText urlInput;
    private Button btnConnect;
    private SharedPreferences preferences;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(Bundle savedInstanceState);

        preferences = getSharedPreferences("wellness_prefs", MODE_PRIVATE);
        String savedUrl = preferences.getString("server_url", null);

        // If URL is already configured, skip setup and load WebView directly
        if (savedUrl != null) {
            launchMainActivity(savedUrl);
            return;
        }

        setContentView(R.layout.activity_url_setup);

        urlInput = findViewById(R.id.urlInput);
        btnConnect = findViewById(R.id.btnConnect);

        btnConnect.setOnClickListener(v -> {
            String url = urlInput.getText().toString().trim();

            if (url.isEmpty()) {
                Toast.makeText(this, "Please enter a URL", Toast.LENGTH_SHORT).show();
                return;
            }

            // Automatically append http:// if user forgets protocol prefix
            if (!url.startsWith("http://") && !url.startsWith("https://")) {
                url = "http://" + url;
            }

            if (!Patterns.WEB_URL.matcher(url).matches()) {
                Toast.makeText(this, "Please enter a valid URL or IP address", Toast.LENGTH_SHORT).show();
                return;
            }

            // Save server URL configuration
            preferences.edit().putString("server_url", url).apply();
            launchMainActivity(url);
        });
    }

    private void launchMainActivity(String url) {
        Intent intent = new Intent(this, MainActivity.class);
        intent.putExtra("url", url);
        startActivity(intent);
        finish();
    }
}
