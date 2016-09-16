using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Windows.Forms;
using System.Drawing;


namespace DeadSectorKiller
{
    class PlotBox: PictureBox
    {
        Graphics gr;
        Graphics bgr;
        Bitmap buffer;
        int cellH;
        int cellW;
        int Ycount;
        int Xcount;
        bool initReady = false;
        public void CreateBox(int arraycount)
        {
            initReady = false;
            gr = this.CreateGraphics();
            buffer = new Bitmap(this.Width, this.Height);
            bgr = Graphics.FromImage(buffer);
            
            double d = 0;
            d = buffer.Width / buffer.Height;
            double d2 = 0;
            d2 = Math.Sqrt(arraycount);
            d2 = d2 * d;
            d2 = Math.Ceiling(d2);
            Xcount = (int)d2;
            d2 = arraycount / d2;
            d2 = Math.Ceiling(d2);
            Ycount = (int)d2;
            cellH = (int)Math.Ceiling((double)((double)buffer.Height / (double)Ycount));
            cellW = (int)Math.Ceiling((double)((double)buffer.Width / (double)Xcount));
            bgr.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            bgr.CompositingQuality = System.Drawing.Drawing2D.CompositingQuality.HighQuality;
            
            for (int x = 0; x < Xcount ; x++)
            {
                for (int y = 0; y < Ycount; y++)
                {
                    bgr.FillRectangle(Brushes.Black  , x * cellW, y * cellH, cellW, cellH);
                    bgr.DrawRectangle(pn, x * cellW, y * cellH, cellW, cellH);
                }
            }
            gr.DrawImage(buffer, new Rectangle(0, 0, buffer.Width , buffer.Height ));
            initReady = true;
        }

        Pen pn = new Pen(Brushes.DarkSlateBlue , (float)1.5);
        double k = 0;
        int xx, yy;
        public void SetColor(int n, Color c)
        {
            if (initReady)
            {
                k = n / Xcount;
                k = Math.Floor(k);
                yy = (int)k;
                yy = yy * cellH;
                k = k * Xcount;
                k = n - k;
                xx = (int)k * cellW;
                bgr.FillRectangle(new SolidBrush(c), xx, yy, cellW, cellH);
                bgr.DrawRectangle(pn, xx, yy, cellW, cellH);
                gr.FillRectangle(new SolidBrush(c), xx, yy, cellW, cellH);
                gr.DrawRectangle(pn, xx, yy, cellW, cellH);
                j++;
                if (j%100==0)
                {
                    gr.DrawImage(buffer, new Rectangle(0, 0, buffer.Width, buffer.Height));
                }
            }
            
            
        }

        int j = 0;
    }
}
